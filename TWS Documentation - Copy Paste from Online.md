TWS Documentation

* Synchronous API  
  * [Introduction](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/introduction)  
  * [TWSSyncWrapper Class](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/tws-sync-wrapper-class)  
  * [Connect & Start Connection](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/connect-start-connection)  
  * [Disconnect & Stop Connection](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/disconnect-stop-connection)  
  * [Current Time](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/current-time)  
  * [Next Valid ID](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/next-valid-id)  
  * [Account Summary](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/account-summary)  
  * [Contract Details](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/contract-details)  
  * [Live Market Data](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/live-market-data)  
  * [Historical Market Data](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/historical-market-data)  
  * [Place Order](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/place-order)  
  * [Cancel Order](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/cancel-order)  
  * [Open Orders](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/open-orders)  
  * [Executions](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/executions)  
  * [Positions](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/positions)  
  * [Portfolio](https://www.interactivebrokers.com/docs/tws-api/doc/synchronous-api/portfolio)

\---

&nbsp;

\#\# title: Introduction

&nbsp;

With the release of TWS API 10.40, Interactive Brokers has introduced the Synchronous API Wrapper class. This class provides a synchronous API structure, combining the functionality of EClient and EWrapper into a beginner-friendly interface.

&nbsp;

The current release is still in a Beta state, slowly rolling out only a portion of what is available in the larger Trader Workstation API configuration. The interface is exclusively available through the \*Python\* programming language.

&nbsp;

The content shown here is an example of what the Sync Wrapper structure looks like. A larger example of all current functionality is available in the 10.40 release of the TWS API under \`{TWS API}/samples/Python/Testbed/sync\_test.py\` .

&nbsp;

\#\#\#\# Request sample

&nbsp;

\`\`\`

\# Import our Sync Wrapper and Contract objects

from ibapi.sync\_wrapper\_alt import \*

from datetime import datetime

&nbsp;

\# Instantiate the reference for our sync class

app \= TWSSyncWrapper(timeout=30)

&nbsp;

\# make a connection to Trader Workstation

\# In this case, we're connecting on Localhost with port 7496 and Client ID 0\.

if not app.connect\_and\_start(host="127.0.0.1", port=7496, client\_id=8675309):

    print("Failed to connect to TWS")

    exit(1)

else:

    print("Connected to TWS")

&nbsp;

\# Create a contract class reference.

\# In our case, we'll be testing with AAPL.

contract \= Contract()

contract.symbol \= "AAPL"

contract.secType \= "STK"

contract.exchange \= "SMART"

contract.primaryExchange \= "ISLAND"

contract.currency \= "USD"

&nbsp;

'''

Contract details requests will return all contracts the match the details

of our contract object in a list. Because a list is returned, we are&nbsp;

taking the first (or 0 index) contract returned.&nbsp;

'''

aapl\_contract \= app.get\_contract\_details(contract)\[0\].contract

print(aapl\_contract)

&nbsp;

market\_data \= app.get\_market\_data\_snapshot(aapl\_contract)

&nbsp;

order \= Order()

order.action \= "BUY"

order.orderType \= "LMT"

order.totalQuantity \= 100

order.lmtPrice \= 258

&nbsp;

order\_status \= app.place\_order\_sync(contract, order)

oid \= order\_status\["orderId"\]

&nbsp;

print(app.get\_open\_orders()\[oid\]\['orderState'\].status)

&nbsp;

print(app.cancel\_order\_sync(oid, OrderCancel()))

&nbsp;

app.disconnect\_and\_stop()

exit()

\`\`\`

&nbsp;

\#\#\#\# Response Sample

&nbsp;

\`\`\`

ERROR \-1 1761170335710 2104 Market data farm connection is OK:usbond

ERROR \-1 1761170335711 2104 Market data farm connection is OK:usfarm.nj

ERROR \-1 1761170335712 2104 Market data farm connection is OK:eufarm

ERROR \-1 1761170335712 2104 Market data farm connection is OK:usfarm

ERROR \-1 1761170335712 2106 HMDS data farm connection is OK:ushmds

ERROR \-1 1761170335713 2158 Sec-def data farm connection is OK:secdefil

Connected to TWS

ConId: 265598, Symbol: AAPL, SecType: STK, LastTradeDateOrContractMonth: , Strike: 0, Right: , Multiplier: , Exchange: SMART, PrimaryExchange: ISLAND, Currency: USD, LocalSymbol: AAPL, TradingClass: NMS, IncludeExpired: False, SecIdType: , SecId: , Description: , IssuerId: Combo:

{'price': {1: {'price': 258.5, 'attrib': 2076793531408: CanAutoExecute: 1, PastLimit: 0, PreOpen: 0}, 2: {'price': 258.65, 'attrib': 2076793531536: CanAutoExecute: 1, PastLimit: 0, PreOpen: 0}, 4: {'price': 258.62, 'attrib': 2076793531600: CanAutoExecute: 0, PastLimit: 0, PreOpen: 0}, 6: {'price': 262.85, 'attrib': 2076793531856: CanAutoExecute: 0, PastLimit: 0, PreOpen: 0}, 7: {'price': 255.43, 'attrib': 2076793531920: CanAutoExecute: 0, PastLimit: 0, PreOpen: 0}, 9: {'price': 262.77, 'attrib': 2076793531984: CanAutoExecute: 0, PastLimit: 0, PreOpen: 0}, 14: {'price': 262.74, 'attrib': 2076793532048: CanAutoExecute: 0, PastLimit: 0, PreOpen: 0}}, 'size': {0: Decimal('1'), 3: Decimal('5'), 5: Decimal('3'), 8: Decimal('449348')}}

PreSubmitted

{'orderId': 358, 'status': 'PreSubmitted', 'filled': Decimal('0'), 'remaining': Decimal('100'), 'avgFillPrice': 0.0, 'permId': 1054257323, 'parentId': 0, 'lastFillPrice': 0.0, 'clientId': 8675309, 'whyHeld': '', 'mktCapPrice': 0.0}

\`\`\`

\---

&nbsp;

\#\# title: TWSSyncWrapper Class

&nbsp;

The TWSSyncWrapper class is produced from the ibapi/sync\\\_wrapper file. Clients looking to utilize the class may seek to replace their typical imports for ibapi/client and ibapi/wrapper with an import for "from ibapi.sync\\\_wrapper import TWSSyncWrapper".

&nbsp;

The TWSSyncWrapper class accepts a single argument, timeout. This will provide a default timeout integer in seconds for all connected functions to work with. If no timeout is specified, a default value of 30 seconds is passed instead.

&nbsp;

Each function supports a timeout argument for unique endpoint timeout behavior.

&nbsp;

\`\`\`

from ibapi.sync\_wrapper import TWSSyncWrapper

&nbsp;

app \= TWSSyncWrapper(timeout=30)

\`\`\`

&nbsp;

\---

&nbsp;

\#\# title: Connect & Start Connection

&nbsp;

After creating the class object reference with sync wrapper, connect\\\_and\\\_start() must be used to connect the Python program with the active Trader Workstation implementation. Identical to EClient's connect() function, connect\\\_and\\\_start() supports arguments for host, port, and client\\\_id.

&nbsp;

\#\#\#\# connect\\\_and\\\_start(

&nbsp;

\*\*host:\*\* String. Determine the connecting host IP for the API to connect to. Connections on the same computer should use "localhost" or "127.0.0.1".

&nbsp;

\*\*port:\*\* Integer. Determine the connecting port number configured in the Global Configuration in the "Socket Port" field.

&nbsp;

Defaults: \\{TWS Live: 7496; TWS Paper: 7497; IBG Live: 4001; IBG Paper: 4002′}

&nbsp;

\*\*client\\\_id:\*\* Integer. Determine the connecting client ID. TWS Supports up to 32 simultaneous API connections.

&nbsp;

Users should connect with a client\\\_id of 0 for \[optimal order management functionality\](/tws-api/doc/order-management/client-id-0-and-the-master-client-id).

&nbsp;

\#\#\#\# )

&nbsp;

\`\`\`

app.connect\_and\_start(host="127.0.0.1", port=7496, client\_id=0)

\`\`\`

&nbsp;

\#\#\#\# Response Object

&nbsp;

While it is not necessary to handle the response from connect\\\_and\\\_start(), the function will return the result of EClient.isConnected() to help with connection validation.

&nbsp;

The function call will return a single Boolean value, True or False, in reference to the connection status at the time of reference.

&nbsp;

Developers may look to implement code such as this that will gracefully handle the connection procedure should it fail to connect rather than proceeding with the rest of the code implementation.

&nbsp;

\`\`\`

\# Connect to TWS

\# If the connection succeeded, notify the user.

\# If the connection fails and False is returned, notify the user and gracefully exit the application.

if not app.connect\_and\_start(host="127.0.0.1", port=7496, client\_id=0):

    print("Failed to connect to TWS")

    exit(1)

else:

    print("Connected to TWS")

\`\`\`

&nbsp;

\---

&nbsp;

\#\# title: Disconnect & Stop Connection

&nbsp;

Once a connection is no longer needed, developers should disconnect the session. This will terminate all ongoing requests through the class's client\\\_id. Connections through any other client ID or port will be unaffected.

&nbsp;

\#\#\#\# disconnect\\\_and\\\_stop() \`app.disconnect\_and\_stop()\` The function call does not return after calling. As a result, None is automatically passed in the event the function is referenced.

&nbsp;

\---

&nbsp;

\#\# title: Current Time

&nbsp;

Whenever a user would need to verify the current time used within Trader Workstation or to verify the connection with the application, users may call the get\\\_current\\\_time() function.

&nbsp;

\#\#\#\# get\\\_current\\\_time(

&nbsp;

\*\*timeout:\*\* Integer. Timeout before the request disconnects. Function-specific timeout default of 1 second.

&nbsp;

)

&nbsp;

\`\`\`

app.get\_current\_time()

\`\`\`

&nbsp;

\#\#\#\# Response Object

&nbsp;

get\\\_current\\\_time() will return the current timestamp as an integer representing an epoch timestamp.

&nbsp;

\`\`\`

1760478515

\`\`\`

\---

&nbsp;

\#\# title: Next Valid ID

&nbsp;

Requests should utilize an unique identifier after each request is submitted.

&nbsp;

The same order identifier cannot be reused except to modify an existing order.

&nbsp;

\#\#\#\# get\\\_next\\\_valid\\\_id(

&nbsp;

\*\*timeout:\*\* Integer. Uses default timeout value passed to TWSSyncClass.

&nbsp;

\#\#\#\# )

&nbsp;

\`\`\`

app.get\_next\_valid\_id()

\`\`\`

&nbsp;

\#\#\#\# Response Object

&nbsp;

Requests to the get\\\_next\\\_valid\\\_id() function will return the next valid order ID, which may be used in order submission.

&nbsp;

\`\`\`

123456789

\`\`\`

\---

&nbsp;

\#\# title: Account Summary

&nbsp;

The get\\\_account\\\_summary() function returns all relevant account details identical to Trader Workstation's "Account" window. Users may query to receive all available data or a narrow window based on the \[Account Summary Tag\](/tws-api/doc/account-portfolio-data/account-summary/account-summary-tags).

&nbsp;

\#\#\#\# get\\\_account\\\_summary(

&nbsp;

\*\*tags:\*\* String. Account summary key value to receive data for. See \[Account Summary Tags\](/tws-api/doc/account-portfolio-data/account-summary/account-summary-tags) for details.

&nbsp;

\*\*group:\*\* String. Indicates a Financial Advisor's allocation group to reference account details for. Non-advisor account structures should always pass "All".

&nbsp;

Default value passed, "All".

&nbsp;

\*\*timeout:\*\* Integer. Timeout before the request disconnects. Function-specific timeout default of 5 second.

&nbsp;

\#\#\#\# )

&nbsp;

\`\`\`

from ibapi.account\_summary\_tags import AccountSummaryTags

&nbsp;

app.get\_account\_summary(AccountSummaryTags.AllTags, "All")

\`\`\`

&nbsp;

Total size of the request may vary depending on number of accounts held in the account, and the number of tags requested.

&nbsp;

\#\#\#\# Response Object

&nbsp;

\*\*\\{AccountId}:\*\* Dictionary. Contains all tag value pairs for the designated accountId.

&nbsp;

\\{

&nbsp;

\*\*\\{Tag}:\*\* Dictionary. Contains the value of the affiliated tag along with the relevant currency.

&nbsp;

\*\*value:\*\* String. Contains the alphanumeric value affiliated with the designated tag.

&nbsp;

\*\*currency:\*\* String. Returns the currency used to denote the value. May return an empty string if returning value does not contain a price.

&nbsp;

}

&nbsp;

\`\`\`

{'U1234567': {'AccountType': {'value': 'LLC', 'currency': ''}, 'Cushion': {'value': '0.993764', 'currency': ''}, 'DayTradesRemaining': {'value': '-1', 'currency': ''}, 'LookAheadNextChange': {'value': '1760558400', 'currency': ''}, 'AccruedCash': {'value': '262079.00', 'currency': 'USD'}, 'AvailableFunds': {'value': '219944453.18', 'currency': 'USD'}, 'BuyingPower': {'value': '1466299088.69', 'currency': 'USD'}, 'EquityWithLoanValue': {'value': '221042710.95', 'currency': 'USD'}, 'ExcessLiquidity': {'value': '220044618.70', 'currency': 'USD'}, 'FullAvailableFunds': {'value': '219944453.18', 'currency': 'USD'}, 'FullExcessLiquidity': {'value': '220044618.70', 'currency': 'USD'}, 'FullInitMarginReq': {'value': '1101020.27', 'currency': 'USD'}, 'FullMaintMarginReq': {'value': '1000859.00', 'currency': 'USD'}, 'GrossPositionValue': {'value': '2982965.22', 'currency': 'USD'}, 'InitMarginReq': {'value': '1101020.27', 'currency': 'USD'}, 'LookAheadAvailableFunds': {'value': '219944453.18', 'currency': 'USD'}, 'LookAheadExcessLiquidity': {'value': '220044618.70', 'currency': 'USD'}, 'LookAheadInitMarginReq': {'value': '1101020.27', 'currency': 'USD'}, 'LookAheadMaintMarginReq': {'value': '1000859.00', 'currency': 'USD'}, 'MaintMarginReq': {'value': '1000859.00', 'currency': 'USD'}, 'NetLiquidation': {'value': '221425500.56', 'currency': 'USD'}, 'PreviousDayEquityWithLoanValue': {'value': '205659145.23', 'currency': 'USD'}, 'TotalCashValue': {'value': '218181198.71', 'currency': 'USD'}}

\`\`\`

\---

&nbsp;

\#\# title: Contract Details

&nbsp;

Interactive Brokers trading is centered around \[Contract Objects\](/tws-api/doc/contracts-financial-instruments/the-contract-object). This is used when submitting requests for market data, retrieving position information, and placing orders. The Synchronous Wrapper utilizes the same \[Contract Object\](/tws-api/doc/contracts-financial-instruments/the-contract-object) as the standard TWS API.

&nbsp;

Passing as much known information through a Contract Details will return all contracts that match the requesting information. At a minimum, the Contract ID, or Symbol and Security Type must be passed for contract discovery.

&nbsp;

\#\#\#\# get\\\_contract\\\_details(

&nbsp;

\*\*contract:\*\* \[Contract Object\](/tws-api/doc/contracts-financial-instruments/the-contract-object). Contract details you are searching for.

&nbsp;

\*\*timeout:\*\* Integer. Timeout before the request disconnects. Function-specific timeout default of 5 second.

&nbsp;

\#\#\#\# )

&nbsp;

\`\`\`

contract \= Contract()

contract.symbol \= "AAPL"

contract.secType \= "STK"

&nbsp;

app.get\_contract\_details(contract=contract)

\`\`\`

&nbsp;

\#\#\#\# Response Object

&nbsp;

The get\\\_contract\\\_details() function will return a list of \[Contract\](/tws-api/doc/contracts-financial-instruments/the-contract-object) objects.\\

Unless a relatively narrow scope is provided during the initial contract details request, multiple contract objects may be returned within the list. Please be aware that directly printing this information may result in the memory address being displayed.

&nbsp;

\`\`\`

\[3039334541648: ConId: 265598, Symbol: AAPL, SecType: STK, LastTradeDateOrContractMonth: , Strike: 0, Right: , Multiplier: , Exchange: SMART, PrimaryExchange: ISLAND, Currency: USD, LocalSymbol: AAPL, TradingClass: NMS, IncludeExpired: False, SecIdType: , SecId: , Description: , IssuerId: Combo:,NMS,0.01,ACTIVETIM,AD,ADDONT,ADJUST,ALERT,ALGO,ALLOC,AON,AVGCOST,BASKET,BENCHPX,CASHQTY,COND,CONDORDER,DARKONLY,DARKPOLL,DAY,DEACT,DEACTDIS,DEACTEOD,DIS,DUR,GAT,GTC,GTD,GTT,HID,IBKRATS,ICE,IMB,IOC,LIT,LMT,LOC,MIDPX,MIT,MKT,MOC,MTL,NGCOMB,NODARK,NONALGO,OCA,OPG,OPGREROUT,PEGBENCH,PEGMID,POSTATS,POSTONLY,PREOPGRTH,PRICECHK,REL,REL2MID,RELPCTOFS,RPI,RTH,SCALE,SCALEODD,SCALERST,SIZECHK,SMARTSTG,SNAPMID,SNAPMKT,SNAPREL,STP,STPLMT,SWEEP,TRAIL,TRAILLIT,TRAILLMT,TRAILMIT,WHATIF,SMART,AMEX,NYSE,CBOE,PHLX,ISE,CHX,ARCA,ISLAND,DRCTEDGE,BEX,BATS,EDGEA,BYX,IEX,EDGX,FOXRIVER,PEARL,NYSENAT,LTSE,MEMX,IBEOS,OVERNIGHT,TPLUS0,PSX,T24X,1,0,APPLE INC,,Technology,Computers,Computers,US/Eastern,20251015:0400-20251015:2000;20251016:0400-20251016:2000;20251017:0400-20251017:2000;20251018:CLOSED;20251019:CLOSED;20251020:0400-20251020:2000,20251015:0930-20251015:1600;20251016:0930-20251016:1600;20251017:0930-20251017:1600;20251018:CLOSED;20251019:CLOSED;20251020:0930-20251020:1600,,0,,,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,1,\[3039334542544: ISIN=US0378331005;\],,COMMON,,,,,,False,False,0,False,,,,,False,,0.0001,0.0001,100,None,,,, 3039334543504: ConId: 273982664,...\]

\`\`\`

\---

&nbsp;

\#\# title: Live Market Data

&nbsp;

Users may request market data using get\\\_market\\\_data\\\_snapshot() to retrieve available market data.\\

The request currently supports \[tickPrice, tickSize, tickString, tickGeneric, tickNews, and tickOptionCompution\](/tws-api/doc/market-data-live/top-of-book-l-1/receive-live-data) data.

&nbsp;

\#\#\#\# get\\\_market\\\_data\\\_snapshot(

&nbsp;

\*\*contract:\*\* \[Contract Object\](/tws-api/doc/contracts-financial-instruments/the-contract-object). Contract to retrieve market data for.

&nbsp;

\*\*generic\\\_tick\\\_list:\*\* String. String containing comma-separate values to determine addition data to retrieve.

&nbsp;

Default: Automatically sends an empty string, returning only the basic data such as Last, Bid, and Ask. See \[Available Tick Types\](/tws-api/doc/market-data-live/available-tick-types/introduction) for more details.

&nbsp;

\*\*snapshot:\*\* Boolean. Determine if a single snapshot should be returned or if data should be continuously updated until the timeout threshold has been reached.

&nbsp;

Default: Set to True, returning a snapshot of data as soon as possible.

&nbsp;

\*\*timeout:\*\* Integer. Uses default timeout value passed to TWSSyncClass.

&nbsp;

\#\#\#\# )

&nbsp;

\`\`\`

contract \= Contract()

contract.symbol \= "AAPL"

contract.secType \= "STK"

contract.exchange \= "SMART"

contract.primaryExchange \= "NASDAQ"

contract.currency \= "USD"

&nbsp;

market\_data \= app.get\_market\_data\_snapshot(contract, "225,232", False)

\`\`\`

&nbsp;

Data returned by get\\\_market\\\_data\\\_snapshot() is delivered as a json dictionary object, separating data into "price" and "size" tags. Values are then returned as the affiliated tick types alongside any price or attribute data.

&nbsp;

\#\#\#\# Response Object

&nbsp;

\\{

&nbsp;

\*\*\\{TickType}:\*\* Integer, Float String. The value of the tag. Can include price values (Float), Size values (Decimal), or direct information (string).

&nbsp;

}

&nbsp;

\`\`\`

{'BID': 276.17, 'BID\_SIZE': Decimal('900'), 'ASK': 276.2, 'ASK\_SIZE': Decimal('300'), 'LAST\_TIMESTAMP': '1764009996', 'LAST': 276.18, 'LAST\_SIZE': Decimal('100'), 'VOLUME': Decimal('271511')}

\`\`\`

&nbsp;

\---

&nbsp;

\#\# title: Historical Market Data

&nbsp;

\#\#\#\# get\\\_historical\\\_data(

&nbsp;

\*\*contract:\*\* \[Contract Object\](/tws-api/doc/contracts-financial-instruments/the-contract-object). Contract to retrieve market data for.

&nbsp;

\*\*end\\\_date\\\_time:\*\* String. The request's end date and time. This should be formatted as "YYYYMMDD HH:mm:ss TMZ". You may also pass an empty string to indicate the current moment\\

Please be aware that endDateTime must be left as an empty string when requesting continuous futures contracts or certain whatToShow values like ADJUSTED\\\_LAST.

&nbsp;

\*\*duration\\\_str:\*\* String. The total timespan the bars should cover. See \[Duration\](/tws-api/doc/market-data-historical/historical-bars/duration) for details.

&nbsp;

\*\*bar\\\_size\\\_setting:\*\* String. The time span covered by each bar. See \[Bar Sizes\](/tws-api/doc/market-data-historical/historical-bars/historical-bar-sizes) for details.

&nbsp;

\*\*what\\\_to\\\_show:\*\* String. Determines what kind of data should be returned. See \[whatToShow\](/tws-api/doc/market-data-historical/historical-bar-what-to-show/introduction) for more details.

&nbsp;

\*\*use\\\_rth:\*\* Boolean. Define if data should only be returned from the regular trading session or if extended trading hours should be included.

&nbsp;

Default: True is passed by default, only returning data from the regular trading sesions.

&nbsp;

\*\*format\\\_date:\*\* Integer. Determine the return structure of the date. Supports (1) to return a datetime formatting string or 2 to return a epoch Unix timestamp.

&nbsp;

Default: Set to 1, returning a datetime string.

&nbsp;

\*\*timeout:\*\* Integer. A default value of 30 is supplied.

&nbsp;

\#\#\#\# )

&nbsp;

\`\`\`

contract \= Contract()

contract.symbol \= "AAPL"

contract.secType \= "STK"

contract.exchange \= "SMART"

contract.primaryExchange \= "NASDAQ"

contract.currency \= "USD"

&nbsp;

app.get\_historical\_data(contract=contract, end\_date\_time="", duration\_str="1 W", bar\_size\_setting="1 day", what\_to\_show="TRADES", use\_rth=True)

\`\`\`

&nbsp;

\#\#\#\# Response Object

&nbsp;

Requesting historical bars will return return a list containing all \\\[Bar\] objects for the duration. Please be aware that directly printing this information may result in the memory address being displayed.

&nbsp;

\`\`\`

\[2524872613328: Date: 20251013, Open: 249.31, High: 249.69, Low: 245.56, Close: 247.66, Volume: 187465.43, WAP: 247.952, BarCount: 105768, 2524872614864: Date: 20251014, Open: 246.6, High: 248.85, Low: 244.7, Close: 247.77, Volume: 176034.99, WAP: 247.21, BarCount: 100507, 2524872615120: Date: 20251015, Open: 249.49, High: 251.82, Low: 247.47, Close: 249.34, Volume: 172136.46, WAP: 249.754, BarCount: 96331, 2524872615248: Date: 20251016, Open: 248.28, High: 249.04, Low: 245.13, Close: 247.45, Volume: 235179.94, WAP: 247.351, BarCount: 132811, 2524872615376: Date: 20251017, Open: 248.08, High: 253.38, Low: 247.27, Close: 252.29, Volume: 260673.48, WAP: 250.408, BarCount: 125863\]

\`\`\`

\---

&nbsp;

\#\# title: Place Order

&nbsp;

\#\#\#\# place\\\_order\\\_sync(

&nbsp;

\*\*contract:\*\* \[Contract Object\](/tws-api/doc/contracts-financial-instruments/the-contract-object). Contract to trade.

&nbsp;

\*\*order:\*\* \[Order Object\](/tws-api/doc/orders/the-order-and-contract-objects). Order parameters to be traded.

&nbsp;

\*\*timeout:\*\* Integer. Uses default timeout value passed to TWSSyncClass. Please be aware the timeout is only relevant for the response details. The order will submit in accordance with the order object's details.

&nbsp;

\#\#\#\# )

&nbsp;

\`\`\`

contract \= Contract()

contract.symbol \= "AAPL"

contract.secType \= "STK"

contract.exchange \= "SMART"

contract.primaryExchange \= "NASDAQ"

contract.currency \= "USD"

&nbsp;

order \= Order()

order.action \= "BUY"

order.orderType \= "LMT"

order.totalQuantity \= 100

order.lmtPrice \= 250

&nbsp;

app.place\_order\_sync(contract, order)

\`\`\`

&nbsp;

Upon placing an order, a dictionary containing all of the order status's information will be returned. As the response is static, refer to the \[get\\\_open\\\_orders\](/tws-api/doc/synchronous-api/open-orders) function more more details on the current order status.

&nbsp;

\#\#\#\# Response Object

&nbsp;

\\{\\

orderId: Integer. The identifier for the order. Relevant for order tracking, modification, and cancellation.\\

status: String. The current status of the order. See \[Order Status\](/tws-api/doc/order-management/order-status/introduction) for more details.\\

filled: Decimal. The total quantity of executed shares for the order.\\

remaining: Decimal. The total quantity of shares that have yet to execute for the order.\\

avgFillPrice: Float. The average execution price across fills.\\

permId: Integer. The permanent identifier for the order. This is calculated based on orderId and client ID for internal order tracking.\\

parentId: Integer. The orderId for the parent of this contract. Will return 0 unless trading a bracket or OCA order.\\

lastFillPrice: Float. The price of the most recent execution for the order.\\

clientId: Integer. The identifier for which client ID the order was placed through. Orders can only be cancelled or modified by their on the \[clientId they are bound to\](/tws-api/doc/orders/modifying-orders).\\

whyHeld: String. In the event an order is held instead of being transmitted, the reason will be documented here.\\

mktCapPrice: Float. If an order is capped due to it exceeding the market price and the price is automatically modified, the modified price will be returned. Otherwise 0.0 is displayed.\\

}

&nbsp;

\`\`\`

{'orderId': 347, 'status': 'PreSubmitted', 'filled': Decimal('0'), 'remaining': Decimal('100'), 'avgFillPrice': 0.0, 'permId': 979867961, 'parentId': 0, 'lastFillPrice': 0.0, 'clientId': 8675309, 'whyHeld': '', 'mktCapPrice': 0.0}

\`\`\`

\---

&nbsp;

\#\# title: Cancel Order

&nbsp;

\#\#\#\# cancel\\\_order\\\_sync(

&nbsp;

\*\*order\\\_id:\*\* Integer. Identifier for the order to cancel. Retrieved from the original \[Order Placement\](/tws-api/doc/synchronous-api/place-order) or \[get\\\_open\\\_orders()\](/tws-api/doc/synchronous-api/open-orders).

&nbsp;

\*\*order:\*\* \[OrderCancel Object\](/tws-api/ref/order-cancel-class-reference). Order cancellation parameters.

&nbsp;

\*\*timeout:\*\* Integer. A default value of 3 seconds is supplied.

&nbsp;

\#\#\#\# )

&nbsp;

\`\`\`

app.cancel\_order\_sync(347, OrderCancel())

\`\`\`

&nbsp;

Upon cancellingan order, a dictionary containing all of the order status's information will be returned. As the response is static, refer to the \[get\\\_open\\\_orders\](/tws-api/doc/synchronous-api/open-orders) function more more details on the current order status.

&nbsp;

\#\#\#\# Response Object

&nbsp;

\\{

&nbsp;

\*\*orderId:\*\* Integer. The identifier for the order. Relevant for order tracking, modification, and cancellation.

&nbsp;

\*\*status:\*\* String. The current status of the order. See \[Order Status\](/tws-api/doc/order-management/order-status/introduction) for more details.

&nbsp;

\*\*filled:\*\* Decimal. The total quantity of executed shares for the order.

&nbsp;

\*\*remaining:\*\* Decimal. The total quantity of shares that have yet to execute for the order.

&nbsp;

\*\*avgFillPrice:\*\* Float. The average execution price across fills.

&nbsp;

\*\*permId:\*\* Integer. The permanent identifier for the order. This is calculated based on orderId and client ID for internal order tracking.

&nbsp;

\*\*parentId:\*\* Integer. The orderId for the parent of this contract. Will return 0 unless trading a bracket or OCA order.

&nbsp;

\*\*lastFillPrice:\*\* Float. The price of the most recent execution for the order.

&nbsp;

\*\*clientId:\*\* Integer. The identifier for which client ID the order was placed through. Orders can only be cancelled or modified by their on the \[clientId\](/tws-api/doc/orders/modifying-orders) they are bound to.

&nbsp;

\*\*whyHeld:\*\* String. In the event an order is held instead of being transmitted, the reason will be documented here.

&nbsp;

\*\*mktCapPrice:\*\* Float. If an order is capped due to it exceeding the market price and the price is automatically modified, the modified price will be returned. Otherwise 0.0 is displayed.

&nbsp;

}

&nbsp;

\`\`\`

{'orderId': 347, 'status': 'PendingCancel', 'filled': Decimal('0'), 'remaining': Decimal('100'), 'avgFillPrice': 0.0, 'permId': 1395073938, 'parentId': 0, 'lastFillPrice': 0.0, 'clientId': 8675309, 'whyHeld': '', 'mktCapPrice': 0.0}

\`\`\`

\---

&nbsp;

\#\# title: Open Orders

&nbsp;

\#\#\#\# get\\\_open\\\_orders(

&nbsp;

\*\*timeout:\*\* Integer. A default value of 3 seconds is supplied.

&nbsp;

\#\#\#\# )

&nbsp;

\`\`\`

app.get\_open\_orders()

\`\`\`

&nbsp;

All orders from the current day's trading session are returned in a dictionary, using the orderId as the key to discover the specific order.

&nbsp;

\#\#\#\# Response Object

&nbsp;

\\{\\

\\{Order ID}: Dictionary. Returns the \[Contract\](/tws-api/doc/contracts-financial-instruments/the-contract-object), \[Order\](/tws-api/doc/orders/the-order-and-contract-objects), and \\\[OrderState\] objects of the affiliated orderId.\\

\\{\\

orderId: Integer. The identifier for the order. Relevant for order tracking, modification, and cancellation.

&nbsp;

\*\*contract:\*\* \[Contract Object\](/tws-api/doc/contracts-financial-instruments/the-contract-object). Contract to trade.

&nbsp;

\*\*order:\*\* \[Order Object\](/tws-api/doc/orders/the-order-and-contract-objects). Parameters for the given order to execute.

&nbsp;

\*\*orderState:\*\* \\\[OrderState Object\]. Current state of the order. Contains margin impact and status details.

&nbsp;

}

&nbsp;

\`\`\`

{351: {'orderId': 351, 'contract': 2172957720272: ConId: 265598, Symbol: AAPL, SecType: STK, LastTradeDateOrContractMonth: , Strike: 0, Right: , Multiplier: , Exchange: SMART, PrimaryExchange: , Currency: USD, LocalSymbol: AAPL, TradingClass: NMS, IncludeExpired: False, SecIdType: , SecId: , Description: , IssuerId: Combo:, 'order': 2172957719120: 351,8675309,979867965: LMT BUY 100@800 GTC, 'orderState': }}

\`\`\`

\---

&nbsp;

\#\# title: Executions

&nbsp;

Request all executions following the Execution Filter's restrictions.

&nbsp;

\#\#\#\# get\\\_executions(

&nbsp;

\*\*exec\\\_filter:\*\* \\\[ExecutionFilter Object\]. Parameters to restrict the Execution data to be returned.

&nbsp;

\*\*timeout:\*\* Integer. A default value of 10 seconds is supplied.

&nbsp;

\#\#\#\# )

&nbsp;

\`\`\`

app.get\_open\_orders()

\`\`\`

&nbsp;

All executions passed in the context of the ExecutionFilter are returned in a list.

&nbsp;

\#\#\#\# Response Object

&nbsp;

\\\[\\{

&nbsp;

\*\*contract:\*\* \[Contract Object\](/tws-api/doc/contracts-financial-instruments/the-contract-object). Contract to trade.

&nbsp;

\*\*execution:\*\* \\\[Execution Object\]. Execution details regarding the recent trade.

&nbsp;

}\]

&nbsp;

\`\`\`

\[{'contract': 1530250139984: ConId: 265598, Symbol: AAPL, SecType: STK, LastTradeDateOrContractMonth: , Strike: 0, Right: , Multiplier: , Exchange: IEX, PrimaryExchange: , Currency: USD, LocalSymbol: AAPL, TradingClass: NMS, IncludeExpired: False, SecIdType: , SecId: , Description: , IssuerId: Combo:, 'execution': 1530250140432: ExecId: 0000e0d5.68fa9014.01.01, Time: 20251022 14:56:24 US/Eastern, Account: U1234567, Exchange: IEX, Side: BOT, Shares: 100, Price: 256.62, PermId: 1395073936, ClientId: 8675309, OrderId: 355, Liquidation: 0, CumQty: 100, AvgPrice: 256.62, OrderRef: , EvRule: , EvMultiplier: 0, ModelCode: , LastLiquidity: 2, PendingPriceRevision: False, Submitter: csdem9545, OptExerciseOrLapseType: None}\]

\`\`\`

&nbsp;

&nbsp;

\---

&nbsp;

\#\# title: Positions

&nbsp;

Request positions for all accounts available to the user.

&nbsp;

\#\#\#\# get\\\_positions(

&nbsp;

\*\*timeout:\*\* Integer. A default value of 10 seconds is supplied.

&nbsp;

\#\#\#\# )

&nbsp;

\`\`\`

app.get\_positions()

\`\`\`

&nbsp;

All orders from the current day's trading session are returned in a dictionary, using the orderId as the key to discover the specific order.

&nbsp;

\#\#\#\# Response Object

&nbsp;

\\{\\

\\{Account ID}: List. List of all contracts\\

\\\[\\{

&nbsp;

\*\*contract:\*\* \[Contract Object\](/tws-api/doc/contracts-financial-instruments/the-contract-object). Contract to trade.

&nbsp;

\*\*position:\*\* Decimal. The total number of shares held in the account.

&nbsp;

\*\*avgCost:\*\* Float. The average price across executions for the position.

&nbsp;

}\]

&nbsp;

\`\`\`

{'U1234567': \[{'contract': 2333839861008: ConId: 340216238, Symbol: COIL, SecType: FUT, LastTradeDateOrContractMonth: 20251031, Strike: 0, Right: , Multiplier: 1000, Exchange: IPE, PrimaryExchange: , Currency: , LocalSymbol: COILZ5, TradingClass: COIL, IncludeExpired: False, SecIdType: , SecId: , Description: , IssuerId: Combo:, 'position': Decimal('4'), 'avgCost': 61359.9}\]}

\`\`\`

&nbsp;

\---

&nbsp;

\#\# title: Portfolio

&nbsp;

Request portfolio details for the selected account or accounts available to the user.

&nbsp;

\#\#\#\# get\\\_portfolio(

&nbsp;

\*\*account\\\_code:\*\* String. The accountID to pull portfolio information for. If an empty string is passed, all accounts are requested.

&nbsp;

\*\*timeout:\*\* Integer. A default value of 10 seconds is supplied.

&nbsp;

\#\#\#\# )

&nbsp;

\`\`\`

app.get\_portfolio("")

\`\`\`

&nbsp;

\#\#\#\# Response Object

&nbsp;

\\{\\

\\{Account ID}: List. List of all contracts\\

\\\[\\{

&nbsp;

\*\*contract:\*\* \[Contract Object\](/tws-api/doc/contracts-financial-instruments/the-contract-object). Contract to trade.

&nbsp;

\*\*position:\*\* Decimal. The total number of shares held in the account.

&nbsp;

\*\*marketPrice:\*\* Float. The current market price of the instrument.

&nbsp;

\*\*marketValue:\*\* Float. The current value of the total position.

&nbsp;

\*\*averageCost:\*\* Float. The average price across executions for the position.

&nbsp;

\*\*unrealizedPNL:\*\* Float. The unrealized profit and loss for the instrument.

&nbsp;

\*\*realizedPNL:\*\* Float. The realized profit and loss for the instrument.

&nbsp;

\*\*accountName:\*\* String. The account identifier that holds the given position.

&nbsp;

}\]

&nbsp;

\`\`\`

\[{'contract': 1957652380880: ConId: 265598, Symbol: AAPL, SecType: STK, LastTradeDateOrContractMonth: , Strike: 0, Right: , Multiplier: , Exchange: ISLAND, PrimaryExchange: , Currency: USD, LocalSymbol: AAPL, TradingClass: NMS, IncludeExpired: False, SecIdType: , SecId: , Description: , IssuerId: Combo:, 'position': Decimal('202635'), 'marketPrice': 258.57998655, 'marketValue': 52397355.58, 'averageCost': 263.3360764, 'unrealizedPNL': \-963750.26, 'realizedPNL': 0.0, 'accountName': 'DU5240685'}\]

\`\`\`

&nbsp;

ERROR HANDLING

\---

&nbsp;

\#\# title: Introduction

&nbsp;

When a client application sends a message to TWS which requires a response which has an expected response (i.e. placing an order, requesting market data, subscribing to account updates, etc.), TWS will almost either always 1\) respond with the relevant data or 2\) send an error message to \[EWrapper.error()\](/tws-api/doc/error-handling/receiving-error-messages).

&nbsp;

\* \*\*Exceptions when no response can occur\*\*: Also, if a request is made prior to full establishment of connection (denoted by a returned 2104 or 2106 error code \*"Data Server is Ok"\*), there may not be a response from the request.

&nbsp;

Error messages sent by the TWS are handled by the \[EWrapper.error()\](/tws-api/doc/error-handling/receiving-error-messages) method. The \[EWrapper.error()\](/tws-api/doc/error-handling/receiving-error-messages) event contains the originating request Id (or the orderId in case the error was raised when placing an order), a numeric error code and a brief description. It is important to keep in mind that this function is used for \*true\* error messages as well as notifications that do not mean anything is wrong.

&nbsp;

\*\*API Error Messages when TWS is not set to the English Language\*\*

&nbsp;

\* Currently on the Windows platform, error messages are sent using Latin1 encoding. If TWS is launched in a non-Western language, it is recommended to enable the setting at Global Configuration \-\> API \-\> Settings to "Show API error messages in English".

&nbsp;

\---

&nbsp;

\#\# title: Understanding Message Codes

&nbsp;

The TWS uses the \[EWrapper.error\](/tws-api/doc/error-handling/receiving-error-messages) method not only to deliver errors but also warnings or informative messages. This is done mostly for simplicity's sake. Below is a table with all the messages which can be sent by the TWS/IB Gateway. All messages delivered by the TWS are usually accompanied by a brief but meaningful description pointing in the direction of the problem.

&nbsp;

Remember that the TWS API simply connects to a running TWS/IB Gateway which most of times will be running on your local network if not in the same host as the client application. It is your responsibility to provide reliable connectivity between the TWS and your client application.

&nbsp;

\---

&nbsp;

\#\# title: System Message Codes

&nbsp;

The messages in the table below are not a consequence of any action performed by the client application. They are notifications about the connectivity status between the TWS and our servers. Your client application must pay special attention to them and handle the situation accordingly. You are very likely to lose connectivity to our servers at least once a day due to our daily server maintenance downtime as clearly detailed in our Current System Status page. Note that after the system reset, the TWS/IB Gateway will automatically reconnect to our servers and you can resume your operations normally.

&nbsp;

\*\*Note:\*\*

&nbsp;

1\. During a reset period, there may be an interruption in the ability to log in or manage orders. Existing orders (native types) will operate normally although execution reports and simulated orders will be delayed until the reset is complete. It is not recommended to operate during the scheduled reset times.

&nbsp;

| Code | TWS message                                                                                                          | Additional notes                                                                                                                                                                |

| \---- | \-------------------------------------------------------------------------------------------------------------------- | \------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| 1100 | Connectivity between IB and the TWS has been lost.                                                                   | Your TWS/IB Gateway has been disconnected from IB servers. This can occur because of an internet connectivity issue, a nightly reset of the IB servers, or a competing session. |

| 1101 | Connectivity between IB and TWS has been restored- data lost.\\\*                                                      | The TWS/IB Gateway has successfully reconnected to IB's servers. Your market data requests have been lost and need to be re-submitted.                                          |

| 1102 | Connectivity between IB and TWS has been restored- data maintained.                                                  | The TWS/IB Gateway has successfully reconnected to IB's servers. Your market data requests have been recovered and there is no need for you to re-submit them.                  |

| 1300 | TWS socket port has been reset and this connection is being dropped. Please reconnect on the new port – \\\<port\\\_num\> | The port number in the TWS/IBG settings has been changed during an active API connection.                                                                                       |--

&nbsp;

\-

&nbsp;

\#\# title: Error Codes

&nbsp;

Error codes in different ranges have different indications.

&nbsp;

| Code           | TWS message                                                                                                                                                                                                                                                                     | Additional notes                                                                                                                                                                                                                                                                                                                                                                                                                         |

| \-------------- | \------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | \---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| 100            | Max rate of messages per second has been exceeded.                                                                                                                                                                                                                              | The client application has exceeded the rate of 50 messages/second. The TWS will likely disconnect the client application after this message.                                                                                                                                                                                                                                                                                            |

| 101            | Max number of tickers has been reached.                                                                                                                                                                                                                                         | "The current number of active market data subscriptions in TWS and the API altogether has been exceeded. This number is calculated based on a formula which is based on the equity, commissions, and quote booster packs in an account. Active lines can be checked in Tws using the Ctrl-Alt-= combination"                                                                                                                             |

| 102            | Duplicate ticker ID.                                                                                                                                                                                                                                                            | A market data request used a ticker ID which is already in use by an active request.                                                                                                                                                                                                                                                                                                                                                     |

| 103            | Duplicate order ID.                                                                                                                                                                                                                                                             | An order was placed with an order ID that is less than or equal to the order ID of a previous order from this client                                                                                                                                                                                                                                                                                                                     |

| 104            | Can't modify a filled order.                                                                                                                                                                                                                                                    | An attempt was made to modify an order which has already been filled by the system.                                                                                                                                                                                                                                                                                                                                                      |

| 105            | Order being modified does not match original order.                                                                                                                                                                                                                             | An order was placed with an order ID of a currently open order but basic parameters differed (aside from quantity or price fields)                                                                                                                                                                                                                                                                                                       |

| 106            | Can't transmit order ID:                                                                                                                                                                                                                                                        | Order ID may not be transmitted. This is most often caused by an invalid order type or order formatting.                                                                                                                                                                                                                                                                                                                                 |

| 107            | Cannot transmit incomplete order.                                                                                                                                                                                                                                               | Order is missing a required field.                                                                                                                                                                                                                                                                                                                                                                                                       |

| 109            | Price is out of the range defined by the Percentage setting at order defaults frame. The order will not be transmitted.                                                                                                                                                         | Price entered is outside the range of prices set in TWS or IB Gateway Order Precautionary Settings                                                                                                                                                                                                                                                                                                                                       |

| 110            | The price does not conform to the minimum price variation for this contract.                                                                                                                                                                                                    | An entered price field has more digits of precision than is allowed for this particular contract. Minimum increment information can be found on the IB Contracts and Securities Search page.                                                                                                                                                                                                                                             |

| 111            | The TIF (Tif type) and the order type are incompatible.                                                                                                                                                                                                                         | The time in force specified cannot be used with this order type. Please refer to order tickets in TWS for allowable combinations.                                                                                                                                                                                                                                                                                                        |

| 113            | The Tif option should be set to DAY for MOC and LOC orders.                                                                                                                                                                                                                     | Market-on-close or Limit-on-close orders should be sent with time in force set to 'DAY'                                                                                                                                                                                                                                                                                                                                                  |

| 114            | Relative orders are valid for stocks only.                                                                                                                                                                                                                                      | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 115            | "Relative orders for US stocks can only be submitted to SMART, SMART\\\_ECN, INSTINET, or PRIMEX."                                                                                                                                                                                | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 116            | The order cannot be transmitted to a dead exchange.                                                                                                                                                                                                                             | Exchange field is invalid.                                                                                                                                                                                                                                                                                                                                                                                                               |

| 117            | The block order size must be at least 50\.                                                                                                                                                                                                                                       | Caused by a block order submission using a quantity less than 50\.                                                                                                                                                                                                                                                                                                                                                                        |

| 118            | VWAP orders must be routed through the VWAP exchange.                                                                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 119            | Only VWAP orders may be placed on the VWAP exchange.                                                                                                                                                                                                                            | "When an order is routed to the VWAP exchange, the type of the order must be defined as 'VWAP'."                                                                                                                                                                                                                                                                                                                                         |

| 120            | It is too late to place a VWAP order for today.                                                                                                                                                                                                                                 | The cutoff has passed for the current day to place VWAP orders.                                                                                                                                                                                                                                                                                                                                                                          |

| 121            | "Invalid BD flag for the order. Check "Destination" and "BD" flag."                                                                                                                                                                                                             | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 122            | No request tag has been found for order:                                                                                                                                                                                                                                        | Caused when request encoding to socket improperly formed.                                                                                                                                                                                                                                                                                                                                                                                |

| 123            | No record is available for conid:                                                                                                                                                                                                                                               | The specified contract ID cannot be found. This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                     |

| 124            | No market rule is available for conid:                                                                                                                                                                                                                                          | Returned in the event a market rule is not applied to a given contract identifier. May be caused when interacting with a non-tradeable instrument such as an Index.                                                                                                                                                                                                                                                                      |

| 125            | Buy price must be the same as the best asking price.                                                                                                                                                                                                                            | Caused by a Buy order exceptionally above the Best Ask price. Please request market data to identify the NBO.                                                                                                                                                                                                                                                                                                                            |

| 126            | Sell price must be the same as the best bidding price.                                                                                                                                                                                                                          | Caused by a Sell order exceptionally below the Best Bid price. Please request market data to identify the NBB.                                                                                                                                                                                                                                                                                                                           |

| 129            | VWAP orders must be submitted at least three minutes before the start time.                                                                                                                                                                                                     | The start time specified in the VWAP order is less than 3 minutes after when it is placed.                                                                                                                                                                                                                                                                                                                                               |

| 131            | "The sweep-to-fill flag and display size are only valid for US stocks routed through SMART, and will be ignored."                                                                                                                                                               | Sweep-to-fill used on an unsupported order type.                                                                                                                                                                                                                                                                                                                                                                                         |

| 132            | This order cannot be transmitted without a clearing account.                                                                                                                                                                                                                    | Order parameters do not include a valid clearing account.                                                                                                                                                                                                                                                                                                                                                                                |

| 133            | Submit new order failed.                                                                                                                                                                                                                                                        | Failure in order submission. May be caused by order parameters or network connectivity.                                                                                                                                                                                                                                                                                                                                                  |

| 134            | Modify order failed.                                                                                                                                                                                                                                                            | Unable to modify an existing order. The order may have already been executed or cancelled. Please request open orders to verify current order status.                                                                                                                                                                                                                                                                                    |

| 135            | Can't find order with ID \=                                                                                                                                                                                                                                                      | An attempt was made to cancel an order not currently in the system.                                                                                                                                                                                                                                                                                                                                                                      |

| 136            | This order cannot be cancelled.                                                                                                                                                                                                                                                 | "An attempt was made to cancel an order than cannot be cancelled, for instance because"                                                                                                                                                                                                                                                                                                                                                  |

| 137            | VWAP orders can only be cancelled up to three minutes before the start time.                                                                                                                                                                                                    | VWAP order cancellation taking place within three minutes of submission.                                                                                                                                                                                                                                                                                                                                                                 |

| 138            | Could not parse ticker request:                                                                                                                                                                                                                                                 | "Ticker symbol cannot be parsed, likely due to the inclusion of invalid symbols or content."                                                                                                                                                                                                                                                                                                                                             |

| 139            | Parsing error:                                                                                                                                                                                                                                                                  | Error in command syntax generated parsing error.                                                                                                                                                                                                                                                                                                                                                                                         |

| 140            | The size value should be an integer:                                                                                                                                                                                                                                            | The size field in the Order class has an invalid type.                                                                                                                                                                                                                                                                                                                                                                                   |

| 141            | The price value should be a double:                                                                                                                                                                                                                                             | A price field in the Order type has an invalid type.                                                                                                                                                                                                                                                                                                                                                                                     |

| 142            | Institutional customer account does not have account info                                                                                                                                                                                                                       | Institutional account structure is not including account details in order submission.                                                                                                                                                                                                                                                                                                                                                    |

| 143            | Requested ID is not an integer number.                                                                                                                                                                                                                                          | The IDs used in API requests must be integer values.                                                                                                                                                                                                                                                                                                                                                                                     |

| 144            | "Order size does not match total share allocation. To adjust the share allocation, right-click on the order and select Modify \> Share Allocation "                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 145            | Error in validating entry fields –                                                                                                                                                                                                                                              | An error occurred with the syntax of a request field.                                                                                                                                                                                                                                                                                                                                                                                    |

| 146            | Invalid trigger method.                                                                                                                                                                                                                                                         | The trigger method specified for a method such as stop or trail stop was not one of the allowable methods.                                                                                                                                                                                                                                                                                                                               |

| 147            | The conditional contract info is incomplete.                                                                                                                                                                                                                                    |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 148            | "Conditional submission of orders is supported for Limit, Market, MidPrice, Relative and Snap order types only. Conditional cancelation of orders is supported for Limit and MidPrice order types only."                                                                        |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 151            | This order cannot be transmitted without a user name.                                                                                                                                                                                                                           | In DDE the user name is a required field in the place order command.                                                                                                                                                                                                                                                                                                                                                                     |

| 152            | "The "hidden" order attribute may not be specified for this order."                                                                                                                                                                                                             | The order in question cannot be placed as a hidden order. See- \[https://www.interactivebrokers.com/en/index.php?f=596\](https://www.interactivebrokers.com/en/index.php?f=596)                                                                                                                                                                                                                                                            |

| 153            | EFPs can only be limit orders.                                                                                                                                                                                                                                                  | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 154            | Orders cannot be transmitted for a halted security.                                                                                                                                                                                                                             | A security was halted for trading when an order was placed.                                                                                                                                                                                                                                                                                                                                                                              |

| 155            | A sizeOp order must have a user name and account.                                                                                                                                                                                                                               | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 156            | A SizeOp order must go to IBSX                                                                                                                                                                                                                                                  | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 157            | An order can be EITHER Iceberg or Discretionary. Please remove either the Discretionary amount or the Display size.                                                                                                                                                             | In the Order class extended attributes the fields 'Iceberg' and 'Discretionary' cannot                                                                                                                                                                                                                                                                                                                                                   |

| 158            | You must specify an offset amount or a percent offset value.                                                                                                                                                                                                                    | TRAIL and TRAIL STOP orders must have an absolute offset amount or offset percentage specified.                                                                                                                                                                                                                                                                                                                                          |

| 159            | The percent offset value must be between 0% and 100%.                                                                                                                                                                                                                           | A percent offset value was specified outside the allowable range of 0% and 100%.                                                                                                                                                                                                                                                                                                                                                         |

| 160            | The size value cannot be zero.                                                                                                                                                                                                                                                  | The size of an order must be a positive quantity.                                                                                                                                                                                                                                                                                                                                                                                        |

| 161            | Cancel attempted when order is not in a cancellable state. Order permId \=                                                                                                                                                                                                       | An attempt was made to cancel an order not active at the time.                                                                                                                                                                                                                                                                                                                                                                           |

| 162            | Historical market data Service error message.                                                                                                                                                                                                                                   |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 163            | The price specified would violate the percentage constraint specified in the default order settings.                                                                                                                                                                            | The order price entered is outside the allowable range specified in the Order Precautionary Settings of TWS or IB Gateway                                                                                                                                                                                                                                                                                                                |

| 164            | There is no market data to check price percent violations.                                                                                                                                                                                                                      | No market data is available for the specified contract to determine whether the specified price is outside the price percent precautionary order setting.                                                                                                                                                                                                                                                                                |

| 165            | Historical market Data Service query message.                                                                                                                                                                                                                                   | "There was an issue with a historical data request, such is no such data in IB's database. Note this message is not specific to the API."                                                                                                                                                                                                                                                                                                |

| 166            | HMDS Expired Contract Violation.                                                                                                                                                                                                                                                | Historical data is not available for the specified expired contract.                                                                                                                                                                                                                                                                                                                                                                     |

| 167            | VWAP order time must be in the future.                                                                                                                                                                                                                                          | The start time of a VWAP order has already passed.                                                                                                                                                                                                                                                                                                                                                                                       |

| 168            | Discretionary amount does not conform to the minimum price variation for this contract.                                                                                                                                                                                         | The discretionary field is specified with a number of degrees of precision higher than what is allowed for a specified contract.                                                                                                                                                                                                                                                                                                         |

| 200            | No security definition has been found for the request.                                                                                                                                                                                                                          | "The specified contract does not match any in IB's database, usually because of an incorrect or missing parameter."                                                                                                                                                                                                                                                                                                                      |

| 200            | The contract description specified for is ambiguous                                                                                                                                                                                                                             | Ambiguity may occur when the contract definition provided is not unique.                                                                                                                                                                                                                                                                                                                                                                 |

| 200            |                                                                                                                                                                                                                                                                                 | "For some stocks that has the same Symbol, Currency and Exchange, you need to specify the IBApi.Contract.PrimaryExch attribute to avoid ambiguity. Please refer to a sample stock contract here."                                                                                                                                                                                                                                        |

| 200            |                                                                                                                                                                                                                                                                                 | "For futures that has multiple multipliers for the same expiration, You need to specify the IBApi.Contract.Multiplier attribute to avoid ambiguity. Please refer to a sample futures contract here."                                                                                                                                                                                                                                     |

| 201            | Order rejected – Reason:                                                                                                                                                                                                                                                        | An attempted order was rejected by the IB servers. See Order Placement Considerations for additional information/considerations for these errors.                                                                                                                                                                                                                                                                                        |

| 202            | Order cancelled – Reason:                                                                                                                                                                                                                                                       | An active order on the IB server was cancelled. See Order Placement Considerations for additional information/considerations for these errors.                                                                                                                                                                                                                                                                                           |

| 203            | The security is not available or allowed for this account.                                                                                                                                                                                                                      | The specified security has a trading restriction with a specific account.                                                                                                                                                                                                                                                                                                                                                                |

| 203            | The contract description specified for %S is ambiguous; you must specify the currency.                                                                                                                                                                                          | The contract definition is incomplete. The currency must be included.                                                                                                                                                                                                                                                                                                                                                                    |

| 300            | Can't find EId with ticker Id:                                                                                                                                                                                                                                                  | An attempt was made to cancel market data for a ticker ID that was not associated with a current subscription. With the DDE API this occurs by clearing the spreadsheet cell.                                                                                                                                                                                                                                                            |

| 301            | Invalid ticker action:                                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 302            | Error parsing stop ticker string:                                                                                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 303            | Invalid action:                                                                                                                                                                                                                                                                 | An action field was specified that is not available for the account. For most accounts this is only BUY or SELL. Some institutional accounts also have the options SSHORT or SLONG available.                                                                                                                                                                                                                                            |

| 304            | Invalid account value action:                                                                                                                                                                                                                                                   |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 305            | "Request parsing error, the request has been ignored."                                                                                                                                                                                                                          | The syntax of a DDE request is invalid.                                                                                                                                                                                                                                                                                                                                                                                                  |

| 306            | Error processing DDE request:                                                                                                                                                                                                                                                   | An issue with a DDE request prevented it from processing.                                                                                                                                                                                                                                                                                                                                                                                |

| 307            | Invalid request topic:                                                                                                                                                                                                                                                          | The 'topic' field in a DDE request is invalid.                                                                                                                                                                                                                                                                                                                                                                                           |

| 308            | Unable to create the 'API' page in TWS as the maximum number of pages already exists.                                                                                                                                                                                           | "An order placed from the API will automatically open a new page in classic TWS, however there are already the maximum number of pages open."                                                                                                                                                                                                                                                                                            |

| 309            | "Max number (3) of market depth requests has been reached. Note: TWS currently limits users to a maximum of 3 distinct market depth requests. This same restriction applies to API clients, however API clients may make multiple market depth requests for the same security." | "Maximum market depth requests exceeded. Please see our Market Data Line Documentation for more information."                                                                                                                                                                                                                                                                                                                            |

| 310            | Can't find the subscribed market depth with tickerId:                                                                                                                                                                                                                           | An attempt was made to cancel market depth for a ticker not currently active.                                                                                                                                                                                                                                                                                                                                                            |

| 311            | The origin is invalid.                                                                                                                                                                                                                                                          | The origin field specified in the Order class is invalid.                                                                                                                                                                                                                                                                                                                                                                                |

| 312            | The combo details are invalid.                                                                                                                                                                                                                                                  | Combination contract specified has invalid parameters.                                                                                                                                                                                                                                                                                                                                                                                   |

| 313            | The combo details for leg " are invalid.                                                                                                                                                                                                                                        | A combo leg was not defined correctly.                                                                                                                                                                                                                                                                                                                                                                                                   |

| 314            | Security type 'BAG' requires combo leg details.                                                                                                                                                                                                                                 | When specifying security type as 'BAG' make sure to also add combo legs with details.                                                                                                                                                                                                                                                                                                                                                    |

| 315            | Stock combo legs are restricted to SMART order routing.                                                                                                                                                                                                                         | Make sure to specify 'SMART' as an exchange when using stock combo contracts.                                                                                                                                                                                                                                                                                                                                                            |

| 316            | Market depth data has been HALTED. Please re-subscribe.                                                                                                                                                                                                                         | You need to re-subscribe to start receiving market depth data again.                                                                                                                                                                                                                                                                                                                                                                     |

| 317            | Market depth data has been RESET. Please empty deep book contents before applying any new entries.                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 319            | Invalid log level                                                                                                                                                                                                                                                               | Make sure that you are setting a log level to a value in range of 1 to 5\.                                                                                                                                                                                                                                                                                                                                                                |

| 320            | Server error when reading an API client request.                                                                                                                                                                                                                                |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 321            | Server error when validating an API client request.                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 322            | Server error when processing an API client request.                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 323            | Server error: cause – s                                                                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 324            | Server error when reading a DDE client request (missing information).                                                                                                                                                                                                           | Make sure that you have specified all the needed information for your request.                                                                                                                                                                                                                                                                                                                                                           |

| 325            | Discretionary orders are not supported for this combination of exchange and order type.                                                                                                                                                                                         | Make sure that you are specifying a valid combination of exchange and order type for the discretionary order.                                                                                                                                                                                                                                                                                                                            |

| 326            | Unable to connect as the client id is already in use. Retry with a unique client id.                                                                                                                                                                                            | Another client application is already connected with the specified client id.                                                                                                                                                                                                                                                                                                                                                            |

| 327            | Only API connections with clientId set to 0 can set the auto bind TWS orders property.                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 328            | Trailing stop orders can be attached to limit or stop-limit orders only.                                                                                                                                                                                                        | Indicates attempt to attach trail stop to order which was not a limit or stop-limit.                                                                                                                                                                                                                                                                                                                                                     |

| 329            | Order modify failed. Cannot change to the new order type.                                                                                                                                                                                                                       | You are not allowed to modify initial order type to the specific order type you are using.                                                                                                                                                                                                                                                                                                                                               |

| 330            | Only FA or STL customers can request managed accounts list.                                                                                                                                                                                                                     | Make sure that your account type is either FA or STL.                                                                                                                                                                                                                                                                                                                                                                                    |

| 331            | Internal error. FA or STL does not have any managed accounts.                                                                                                                                                                                                                   | You do not have any managed accounts.                                                                                                                                                                                                                                                                                                                                                                                                    |

| 332            | The account codes for the order profile are invalid.                                                                                                                                                                                                                            | You need to check that the account codes you specified for your request are valid.                                                                                                                                                                                                                                                                                                                                                       |

| 333            | Invalid share allocation syntax.                                                                                                                                                                                                                                                |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 334            | Invalid Good Till Date order                                                                                                                                                                                                                                                    | Check you order settings.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 335            | Invalid delta: The delta must be between 0 and 100\.                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 336            | "The time or time zone is invalid. The correct format is hh:mm:ss xxx where xxx is an optionally specified time-zone. E.g.: 15:59:00 EST Note that there is a space between the time and the time zone. If no time zone is specified, local time is assumed."                   |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 337            | "The date, time, or time-zone entered is invalid. The correct format is yyyymmdd hh:mm:ss xxx where yyyymmdd and xxx are optional. E.g.: 20031126 15:59:00 ESTNote that there is a space between the date and time, and between the time and time-zone."                        |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 338            | Good After Time orders are currently disabled on this exchange.                                                                                                                                                                                                                 |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 339            | Futures spread are no longer supported. Please use combos instead.                                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 340            | Invalid improvement amount for box auction strategy.                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 341            | "Invalid delta. Valid values are from 1 to 100\. You can set the delta from the "Pegged to Stock" section of the Order Ticket Panel, or by selecting Page/Layout from the main menu and adding the Delta column."                                                                |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 342            | Pegged order is not supported on this exchange.                                                                                                                                                                                                                                 | You can review all order types and supported exchanges on the Order Types and Algos page.                                                                                                                                                                                                                                                                                                                                                |

| 343            | "The date, time, or time-zone entered is invalid. The correct format is yyyymmdd hh:mm:ss xxx"                                                                                                                                                                                  |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 344            | The account logged into is not a financial advisor account.                                                                                                                                                                                                                     | You are trying to perform an action that is only available for the financial advisor account.                                                                                                                                                                                                                                                                                                                                            |

| 345            | Generic combo is not supported for FA advisor account.                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 346            | Not an institutional account or an away clearing account.                                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 347            | Short sale slot value must be 1 (broker holds shares) or 2 (delivered from elsewhere).                                                                                                                                                                                          | Make sure that your slot value is either 1 or 2\.                                                                                                                                                                                                                                                                                                                                                                                         |

| 348            | Order not a short sale – type must be SSHORT to specify short sale slot.                                                                                                                                                                                                        | Make sure that the action you specified is 'SSHORT'.                                                                                                                                                                                                                                                                                                                                                                                     |

| 349            | "Generic combo does not support "Good After" attribute."                                                                                                                                                                                                                        |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 350            | Minimum quantity is not supported for best combo order.                                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 351            | "The "Regular Trading Hours only" flag is not valid for this order."                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 352            | Short sale slot value of 2 (delivered from elsewhere) requires location.                                                                                                                                                                                                        | You need to specify designatedLocation for your order.                                                                                                                                                                                                                                                                                                                                                                                   |

| 353            | Short sale slot value of 1 requires no location be specified.                                                                                                                                                                                                                   | You do not need to specify designatedLocation for your order.                                                                                                                                                                                                                                                                                                                                                                            |

| 354            | Requested market data is not subscribed. Check API status by selecting the Account menu then under Management choose Market Data Subscription Manager and/or availability of delayed data.                                                                                      | You do not have live market data available in your account for the specified instruments. For further details please refer to our \\\[Market Data Subscriptions page\].                                                                                                                                                                                                                                                                     |

| 355            | Order size does not conform to market rule.                                                                                                                                                                                                                                     | Check order size parameters for the specified contract from the TWS Contract Details.                                                                                                                                                                                                                                                                                                                                                    |

| 356            | Smart-combo order does not support OCA group.                                                                                                                                                                                                                                   | Remove OCA group from your order.                                                                                                                                                                                                                                                                                                                                                                                                        |

| 357            | Your client version is out of date.                                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 358            | Smart combo child order not supported.                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 359            | Combo order only supports reduce on fill without block(OCA).                                                                                                                                                                                                                    |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 360            | No whatif check support for smart combo order.                                                                                                                                                                                                                                  | Pre-trade commissions and margin information is not available for this type of order.                                                                                                                                                                                                                                                                                                                                                    |

| 361            | Invalid trigger price.                                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 362            | Invalid adjusted stop price.                                                                                                                                                                                                                                                    |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 363            | Invalid adjusted stop limit price.                                                                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 364            | Invalid adjusted trailing amount.                                                                                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 365            | No scanner subscription found for ticker id:                                                                                                                                                                                                                                    | Scanner market data subscription request with this ticker id has either been cancelled or is not found.                                                                                                                                                                                                                                                                                                                                  |

| 366            | No historical data query found for ticker id:                                                                                                                                                                                                                                   | Historical market data request with this ticker id has either been cancelled or is not found.                                                                                                                                                                                                                                                                                                                                            |

| 367            | Volatility type if set must be 1 or 2 for VOL orders. Do not set it for other order types.                                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 368            | Reference Price Type must be 1 or 2 for dynamic volatility management. Do not set it for non-VOL orders.                                                                                                                                                                        |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 369            | Volatility orders are only valid for US options.                                                                                                                                                                                                                                | Make sure that you are placing an order for US OPT contract.                                                                                                                                                                                                                                                                                                                                                                             |

| 370            | "Dynamic Volatility orders must be SMART routed, or trade on a Price Improvement Exchange."                                                                                                                                                                                     |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 371            | VOL order requires positive floating point value for volatility. Do not set it for other order types.                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 372            | Cannot set dynamic VOL attribute on non-VOL order.                                                                                                                                                                                                                              | Make sure that your order type is 'VOL'.                                                                                                                                                                                                                                                                                                                                                                                                 |

| 373            | Can only set stock range attribute on VOL or RELATIVE TO STOCK order.                                                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 374            | "If both are set, the lower stock range attribute must be less than the upper stock range attribute."                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 375            | Stock range attributes cannot be negative.                                                                                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 376            | The order is not eligible for continuous update. The option must trade on a cheap-to-reroute exchange.                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 377            | Must specify valid delta hedge order aux. price.                                                                                                                                                                                                                                |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 378            | Delta hedge order type requires delta hedge aux. price to be specified.                                                                                                                                                                                                         | Make sure your order has delta attribute.                                                                                                                                                                                                                                                                                                                                                                                                |

| 379            | Delta hedge order type requires that no delta hedge aux. price be specified.                                                                                                                                                                                                    | Make sure you do not specify aux. delta hedge price.                                                                                                                                                                                                                                                                                                                                                                                     |

| 380            | This order type is not allowed for delta hedge orders.                                                                                                                                                                                                                          | "Limit, Market or Relative orders are supported."                                                                                                                                                                                                                                                                                                                                                                                        |

| 381            | Your DDE.dll needs to be upgraded.                                                                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 382            | The price specified violates the number of ticks constraint specified in the default order settings.                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 383            | The size specified violates the size constraint specified in the default order settings.                                                                                                                                                                                        |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 384            | Invalid DDE array request.                                                                                                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 385            | Duplicate ticker ID for API scanner subscription.                                                                                                                                                                                                                               | Make sure you are using a unique ticker ID for your new scanner subscription.                                                                                                                                                                                                                                                                                                                                                            |

| 386            | Duplicate ticker ID for API historical data query.                                                                                                                                                                                                                              | Make sure you are using a unique ticker ID for your new historical market data query.                                                                                                                                                                                                                                                                                                                                                    |

| 387            | Unsupported order type for this exchange and security type.                                                                                                                                                                                                                     | You can review all order types and supported exchanges on the Order Types and Algos page.                                                                                                                                                                                                                                                                                                                                                |

| 388            | Order size is smaller than the minimum requirement.                                                                                                                                                                                                                             | Check order size parameters for the specified contract from the TWS Contract Details.                                                                                                                                                                                                                                                                                                                                                    |

| 389            | Supplied routed order ID is not unique.                                                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 390            | Supplied routed order ID is invalid.                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 391            | The time or time-zone entered is invalid. The correct format is hh:mm:ss xxx                                                                                                                                                                                                    |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 392            | Invalid order: contract expired.                                                                                                                                                                                                                                                | You can not place an order for the expired contract.                                                                                                                                                                                                                                                                                                                                                                                     |

| 393            | Short sale slot may be specified for delta hedge orders only.                                                                                                                                                                                                                   |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 394            | Invalid Process Time: must be integer number of milliseconds between 100 and 2000\. Found:                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 395            | "Due to system problems, orders with OCA groups are currently not being accepted."                                                                                                                                                                                              | Check TWS bulletins for more information.                                                                                                                                                                                                                                                                                                                                                                                                |

| 396            | "Due to system problems, application is currently accepting only Market and Limit orders for this contract."                                                                                                                                                                    | Check TWS bulletins for more information.                                                                                                                                                                                                                                                                                                                                                                                                |

| 397            | "Due to system problems, application is currently accepting only Market and Limit orders for this contract."                                                                                                                                                                    |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 398            | cannot be used as a condition trigger.                                                                                                                                                                                                                                          | Please make sure that you specify a valid condition                                                                                                                                                                                                                                                                                                                                                                                      |

| 399            | Order message error                                                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 400            | Algo order error.                                                                                                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 401            | Length restriction.                                                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 402            | Conditions are not allowed for this contract.                                                                                                                                                                                                                                   | Condition order type does not support for this contract                                                                                                                                                                                                                                                                                                                                                                                  |

| 403            | Invalid stop price.                                                                                                                                                                                                                                                             | The Stop Price you specified for the order is invalid for the contract                                                                                                                                                                                                                                                                                                                                                                   |

| 404            | Shares for this order are not immediately available for short sale. The order will be held while we attempt to locate the shares.                                                                                                                                               | You order is held by the TWS because you are trying to sell a contract but you do not have any long position and the market does not have short sale available. You order will be transmitted once there is short sale available on the market                                                                                                                                                                                           |

| 405            | The child order quantity should be equivalent to the parent order size.                                                                                                                                                                                                         | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 406            | The currency is not allowed.                                                                                                                                                                                                                                                    | Please specify a valid currency                                                                                                                                                                                                                                                                                                                                                                                                          |

| 407            | The symbol should contain valid non-unicode characters only.                                                                                                                                                                                                                    | Please check your contract Symbol                                                                                                                                                                                                                                                                                                                                                                                                        |

| 408            | Invalid scale order increment.                                                                                                                                                                                                                                                  |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 409            | Invalid scale order. You must specify order component size.                                                                                                                                                                                                                     | ScaleInitLevelSize specified is invalid                                                                                                                                                                                                                                                                                                                                                                                                  |

| 410            | Invalid subsequent component size for scale order.                                                                                                                                                                                                                              | ScaleSubsLevelSize specified is invalid                                                                                                                                                                                                                                                                                                                                                                                                  |

| 411            | "The "Outside Regular Trading Hours" flag is not valid for this order."                                                                                                                                                                                                         | Trading outside of regular trading hours is not available for this security                                                                                                                                                                                                                                                                                                                                                              |

| 412            | The contract is not available for trading.                                                                                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 413            | What-if order should have the transmit flag set to true.                                                                                                                                                                                                                        | You need to set IBApi.Order.Transmit to TRUE                                                                                                                                                                                                                                                                                                                                                                                             |

| 414            | Snapshot market data subscription is not applicable to generic ticks.                                                                                                                                                                                                           | You must leave Generic Tick List to be empty when requesting snapshot market data                                                                                                                                                                                                                                                                                                                                                        |

| 415            | Wait until previous RFQ finishes and try again.                                                                                                                                                                                                                                 |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 416            | RFQ is not applicable for the contract. Order ID:                                                                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 417            | Invalid initial component size for scale order.                                                                                                                                                                                                                                 | ScaleInitLevelSize specified is invalid                                                                                                                                                                                                                                                                                                                                                                                                  |

| 418            | Invalid scale order profit offset.                                                                                                                                                                                                                                              | ScaleProfitOffset specified is invalid                                                                                                                                                                                                                                                                                                                                                                                                   |

| 419            | Missing initial component size for scale order.                                                                                                                                                                                                                                 | You need to specify the ScaleInitLevelSize                                                                                                                                                                                                                                                                                                                                                                                               |

| 420            | Invalid real-time query.                                                                                                                                                                                                                                                        | Information about pacing violations                                                                                                                                                                                                                                                                                                                                                                                                      |

| 421            | Invalid route.                                                                                                                                                                                                                                                                  | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 422            | The account and clearing attributes on this order may not be changed.                                                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 423            | Cross order RFQ has been expired. THI committed size is no longer available. Please open order dialog and verify liquidity allocation.                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 424            | FA Order requires allocation to be specified.                                                                                                                                                                                                                                   | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 425            | FA Order requires per-account manual allocations because there is no common clearing instruction. Please use order dialog Adviser tab to enter the allocation.                                                                                                                  | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 426            | None of the accounts have enough shares.                                                                                                                                                                                                                                        | You are not able to enter short position with Cash Account                                                                                                                                                                                                                                                                                                                                                                               |

| 427            | Mutual Fund order requires monetary value to be specified.                                                                                                                                                                                                                      | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 428            | Mutual Fund Sell order requires shares to be specified.                                                                                                                                                                                                                         | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 429            | Delta neutral orders are only supported for combos (BAG security type).                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 430            | "We are sorry, but fundamentals data for the security specified is not available."                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 431            | What to show field is missing or incorrect.                                                                                                                                                                                                                                     | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 432            | Commission must not be negative.                                                                                                                                                                                                                                                | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 433            | "Invalid "Restore size after taking profit" for multiple account allocation scale order."                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 434            | The order size cannot be zero.                                                                                                                                                                                                                                                  |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 435            | You must specify an account.                                                                                                                                                                                                                                                    | The function you invoked only works on a single account                                                                                                                                                                                                                                                                                                                                                                                  |

| 436            | "You must specify an allocation (either a single account, group, or profile)."                                                                                                                                                                                                  | "When you try to place an order with a Financial Advisor account, you must specify the order to be routed to either a single account, a group, or a profile."                                                                                                                                                                                                                                                                            |

| 437            | Order can have only one flag Outside RTH or Allow PreOpen.                                                                                                                                                                                                                      | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 438            | The application is now locked.                                                                                                                                                                                                                                                  | This error is deprecated.                                                                                                                                                                                                                                                                                                                                                                                                                |

| 439            | Order processing failed. Algorithm definition not found.                                                                                                                                                                                                                        | Please double check your specification for IBApi.Order.AlgoStrategy and IBApi.Order.AlgoParams                                                                                                                                                                                                                                                                                                                                           |

| 440            | Order modify failed. Algorithm cannot be modified.                                                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 441            | Algo attributes validation failed:                                                                                                                                                                                                                                              | Please double check your specification for IBApi.Order.AlgoStrategy and IBApi.Order.AlgoParams                                                                                                                                                                                                                                                                                                                                           |

| 442            | Specified algorithm is not allowed for this order.                                                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 443            | Order processing failed. Unknown algo attribute.                                                                                                                                                                                                                                | Specification for IBApi.Order.AlgoParams is incorrect                                                                                                                                                                                                                                                                                                                                                                                    |

| 444            | Volatility Combo order is not yet acknowledged. Cannot submit changes at this time.                                                                                                                                                                                             | The order is not in a state that is able to be modified                                                                                                                                                                                                                                                                                                                                                                                  |

| 445            | The RFQ for this order is no longer valid.                                                                                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 446            | Missing scale order profit offset.                                                                                                                                                                                                                                              | ScaleProfitOffset is not properly specified                                                                                                                                                                                                                                                                                                                                                                                              |

| 447            | Missing scale price adjustment amount or interval.                                                                                                                                                                                                                              | ScalePriceAdjustValue or ScalePriceAdjustInterval is not specified properly                                                                                                                                                                                                                                                                                                                                                              |

| 448            | Invalid scale price adjustment interval.                                                                                                                                                                                                                                        | ScalePriceAdjustInterval specified is invalid                                                                                                                                                                                                                                                                                                                                                                                            |

| 449            | Unexpected scale price adjustment amount or interval.                                                                                                                                                                                                                           | ScalePriceAdjustValue or ScalePriceAdjustInterval specified is invalid                                                                                                                                                                                                                                                                                                                                                                   |

| 481            | Order size reduced.                                                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 501            | Already Connected.                                                                                                                                                                                                                                                              | Your client application is already connected to the TWS.                                                                                                                                                                                                                                                                                                                                                                                 |

| 502            | "Couldn't connect to TWS. Confirm that "Enable ActiveX and Socket Clients" is enabled and connection port is the same as "Socket Port" on the TWS "Edit-\>Global Configuration…-\>API-\>Settings" menu."                                                                           | When you receive this error message it is either because you have not enabled API connectivity in the TWS and/or you are trying to connect on the wrong port. Refer to the TWS' API Settings as explained in the error message. See also Connectivity                                                                                                                                                                                    |

| 503            | The TWS is out of date and must be upgraded.                                                                                                                                                                                                                                    | Indicates TWS or IBG is too old for use with the current API version. Can also be triggered if the TWS version does not support a specific API function.                                                                                                                                                                                                                                                                                 |

| 504            | Not connected.                                                                                                                                                                                                                                                                  | You are trying to perform a request without properly connecting and/or after connection to the TWS has been broken probably due to an unhandled exception within your client application.                                                                                                                                                                                                                                                |

| 505            | Fatal Error: Unknown message id.                                                                                                                                                                                                                                                |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 506            | Unsupported Version (not used in Python client)                                                                                                                                                                                                                                 |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 507            | Bad Message Length (Java-only)                                                                                                                                                                                                                                                  | "Indicates EOF exception was caught while reading from the socket. This can occur if there is an attempt to connect to TWS with a client ID that is already in use, or if TWS is locked, closes, or breaks the connection. It should be handled by the client application and used to indicate that the socket connection is not valid."                                                                                                 |

| 508            | Bad Message                                                                                                                                                                                                                                                                     |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 509            | Exception caught while reading socket                                                                                                                                                                                                                                           | (not used in Python C\# client)                                                                                                                                                                                                                                                                                                                                                                                                           |

| 510            | Request Market Data Sending Error –                                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 511            | Cancel Market Data Sending Error –                                                                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 512            | Order Sending Error –                                                                                                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 513            | Account Update Request Sending Error –                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 514            | Request For Executions Sending Error –                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 515            | Cancel Order Sending Error –                                                                                                                                                                                                                                                    |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 516            | Request Open Order Sending Error –                                                                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 517            | Unknown contract. Verify the contract details supplied. (not used in Python C\# client)                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 518            | Request Contract Data Sending Error –                                                                                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 519            | Request Market Depth Sending Error –                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 520            | Failed to create socket (not used in C\# client)                                                                                                                                                                                                                                 |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 521            | Set Server Log Level Sending Error –                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 522            | FA Information Request Sending Error –                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 523            | FA Information Replace Sending Error –                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 524            | Request Scanner Subscription Sending Error –                                                                                                                                                                                                                                    |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 525            | Cancel Scanner Subscription Sending Error –                                                                                                                                                                                                                                     |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 526            | Request Scanner Parameter Sending Error –                                                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 527            | Request Historical Data Sending Error –                                                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 528            | Request Historical Data Sending Error –                                                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 529            | Request Real-time Bar Data Sending Error –                                                                                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 530            | Cancel Real-time Bar Data Sending Error –                                                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 531            | Request Current Time Sending Error –                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 532            | Request Fundamental Data Sending Error –                                                                                                                                                                                                                                        |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 533            | Cancel Fundamental Data Sending Error –                                                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 534            | Request Calculate Implied Volatility Sending Error –                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 535            | Request Calculate Option Price Sending Error –                                                                                                                                                                                                                                  |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 536            | Cancel Calculate Implied Volatility Sending Error –                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 537            | Cancel Calculate Option Price Sending Error –                                                                                                                                                                                                                                   |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 538            | Request Global Cancel Sending Error –                                                                                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 539            | Request Market Data Type Sending Error –                                                                                                                                                                                                                                        |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 540            | Request Positions Sending Error –                                                                                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 541            | Cancel Positions Sending Error –                                                                                                                                                                                                                                                |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 542            | Request Account Data Sending Error –                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 543            | Cancel Account Data Sending Error –                                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 544            | Verify Request Sending Error –                                                                                                                                                                                                                                                  |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 545            | Verify Message Sending Error –                                                                                                                                                                                                                                                  |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 546            | Query Display Groups Sending Error –                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 547            | Subscribe To Group Events Sending Error –                                                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 548            | Update Display Group Sending Error –                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 549            | Unsubscribe From Group Events Sending Error –                                                                                                                                                                                                                                   |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 550            | Start API Sending Error –                                                                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 551            | Verify And Auth Request Sending Error –                                                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 552            | Verify And Auth Message Sending Error –                                                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 553            | Request Positions Multi Sending Error –                                                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 554            | Cancel Positions Multi Sending Error –                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 555            | Request Account Updates Multi Sending Error –                                                                                                                                                                                                                                   |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 556            | Cancel Account Updates Multi Sending Error –                                                                                                                                                                                                                                    |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 557            | Request Security Definition Option Params Sending Error –                                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 558            | Request Soft Dollar Tiers Sending Error –                                                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 559            | Request Family Codes Sending Error –                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 560            | Request Matching Symbols Sending Error –                                                                                                                                                                                                                                        |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 561            | Request Market Depth Exchanges Sending Error –                                                                                                                                                                                                                                  |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 562            | Request Smart Components Sending Error –                                                                                                                                                                                                                                        |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 563            | Request News Providers Sending Error –                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 564            | Request News Article Sending Error –                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 565            | Request Historical News Sending Error –                                                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 566            | Request Head Time Stamp Sending Error –                                                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 567            | Request Histogram Data Sending Error –                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 568            | Cancel Request Histogram Data Sending Error –                                                                                                                                                                                                                                   |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 569            | Cancel Head Time Stamp Sending Error –                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 570            | Request Market Rule Sending Error –                                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 571            | Request PnL Sending Error –                                                                                                                                                                                                                                                     |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 572            | Cancel PnL Sending Error –                                                                                                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 573            | Request PnL Single Error –                                                                                                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 574            | Cancel PnL Single Sending Error –                                                                                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 575            | Request Historical Ticks Error –                                                                                                                                                                                                                                                |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 576            | Request Tick-By-Tick Data Sending Error –                                                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 577            | Cancel Tick-By-Tick Data Sending Error –                                                                                                                                                                                                                                        |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 578            | Request Completed Orders Sending Error –                                                                                                                                                                                                                                        |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 579            | Invalid symbol in string –                                                                                                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 580            | Request WSH Meta Data Sending Error –                                                                                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 581            | Cancel WSH Meta Data Sending Error –                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 582            | Request WSH Event Data Sending Error –                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 583            | Cancel WSH Event Data Sending Error –                                                                                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 584            | Request User Info Sending Error –                                                                                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 585            | "FA Profile is not supported anymore, use FA Group instead"                                                                                                                                                                                                                     | "Indicates FaDataTypeEnum.PROFILES is deprecated. Use FaDataTypeEnum.GROUPS or 1 instead"                                                                                                                                                                                                                                                                                                                                                |

| 586            | Failed to read message because not connected (Used only in Java client)                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 587            | Request Current Time In Millis Sending Error –                                                                                                                                                                                                                                  |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 588            | Error encoding protobuf                                                                                                                                                                                                                                                         | (Used only in Java client)                                                                                                                                                                                                                                                                                                                                                                                                               |

| 589            | Cancel Market Depth Sending Error –                                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 2100           | New account data requested from TWS. API client has been unsubscribed from account data.                                                                                                                                                                                        | "The TWS only allows one IBApi.EClient.reqAccountUpdates request at a time. If the client application attempts to subscribe to a second account without canceling the previous subscription, the new request will override the old one and the TWS will send this message notifying so."                                                                                                                                                 |

| 2101           | Unable to subscribe to account as the following clients are subscribed to a different account.                                                                                                                                                                                  | "If a client application invokes IBApi.EClient.reqAccountUpdates when there is an active subscription started by a different client, the TWS will reject the new subscription request with this message."                                                                                                                                                                                                                                |

| 2102           | Unable to modify this order as it is still being processed.                                                                                                                                                                                                                     | "If you attempt to modify an order before it gets processed by the system, the modification will be rejected. Wait until the order has been fully processed before modifying it. See Placing Orders for further details."                                                                                                                                                                                                                |

| 2103           | A market data farm is disconnected.                                                                                                                                                                                                                                             | "Indicates a connectivity problem to an IB server. Outside of the nightly IB server reset, this typically indicates an underlying ISP connectivity issue."                                                                                                                                                                                                                                                                               |

| 2104           | Market data farm connection is OK                                                                                                                                                                                                                                               | "A notification that connection to the market data server is ok. This is a notification and not a true error condition, and is expected on first establishing connection."                                                                                                                                                                                                                                                               |

| 2105           | A historical data farm is disconnected.                                                                                                                                                                                                                                         | "Indicates a connectivity problem to an IB server. Outside of the nightly IB server reset, this typically indicates an underlying ISP connectivity issue."                                                                                                                                                                                                                                                                               |

| 2106           | A historical data farm is connected.                                                                                                                                                                                                                                            | "A notification that connection to the market data server is ok. This is a notification and not a true error condition, and is expected on first establishing connection."                                                                                                                                                                                                                                                               |

| 2107           | A historical data farm connection has become inactive but should be available upon demand.                                                                                                                                                                                      | "Whenever a connection to the historical data farm is not being used because there is not an active historical data request, the connection will go inactive in IB Gateway. This does not indicate any connectivity issue or problem with IB Gateway. As soon as a historical data request is made the status will change back to active."                                                                                               |

| 2108           | A market data farm connection has become inactive but should be available upon demand.                                                                                                                                                                                          | "Whenever a connection to our data farms is not needed, it will become dormant. There is nothing abnormal nor wrong with your client application nor with the TWS. You can safely ignore this message."                                                                                                                                                                                                                                  |

| 2109           | "Order Event Warning: Attribute "Outside Regular Trading Hours" is ignored based on the order type and destination. PlaceOrder is now processed."                                                                                                                               | Indicates the outsideRth flag was set for an order for which there is not a regular vs outside regular trading hour distinction                                                                                                                                                                                                                                                                                                          |

| 2110           | Connectivity between TWS and server is broken. It will be restored automatically.                                                                                                                                                                                               | Indicates a connectivity problem between TWS or IBG and the IB server. This will usually only occur during the IB nightly server reset; cases at other times indicate a problem in the local ISP connectivity.                                                                                                                                                                                                                           |

| 2111           | "The Start and/or End Time for algo order BUY/SELL a contract was adjusted to use the next trading date. To modify this setting, use the Auto-adjust algo order date item on the Orders configuration page"                                                                     | Please go to TWS Global Configuration – "Orders" – "Settings" to correct the configuration.                                                                                                                                                                                                                                                                                                                                              |

| 2119           | Market data farm is connecting.                                                                                                                                                                                                                                                 |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 2130           | Warning: products are trading on the basis of currency price with factor.                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 2137           | Cross Side Warning                                                                                                                                                                                                                                                              | "This warning message occurs in TWS version 955 and higher. It occurs when an order will change the position in an account from long to short or from short to long. To bypass the warning, a new feature has been added to IB Gateway 956 (or higher) and TWS 957 (or higher) so that once can go to Global Configuration \> Messages and disable the "Cross Side Warning"."                                                             |

| 2152           | Market depth smart depth exchanges.                                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 2158           | Sec-def data farm connection is OK                                                                                                                                                                                                                                              | "A notification that connection to the Security definition data server is ok. This is a notification and not a true error condition, and is expected on first establishing connection."                                                                                                                                                                                                                                                  |

| 2168           | Etrade Only Not Supported Warning                                                                                                                                                                                                                                               | The EtradeOnly IBApi.Order attribute is no longer supported. Error received with TWS versions 983+. Remove attribute to place order.                                                                                                                                                                                                                                                                                                     |

| 2169           | Firm Quote Only Not Supported Warning                                                                                                                                                                                                                                           | The firmQuoteOnly IBApi.Order attribute is no longer supported. Error received with TWS versions 983+. Remove attribute to place order.                                                                                                                                                                                                                                                                                                  |

| 2188           | Up-to-the-second historical data requires additional subscription for the API.                                                                                                                                                                                                  | Historical data requests within 15 minutes of the current time require a valid market data subscription. See our \[Market Data Subscriptions\](/general/market-data-subscriptions/tws-data-vs-api-data) page for more details.                                                                                                                                                                                                             |

| 10000          | Cross currency combo error.                                                                                                                                                                                                                                                     |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10001          | Cross currency vol error.                                                                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10002          | Invalid non-guaranteed legs.                                                                                                                                                                                                                                                    |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10003          | IBSX not allowed.                                                                                                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10005          | Read-only models.                                                                                                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10006          | Missing parent order.                                                                                                                                                                                                                                                           | The parent order ID specified cannot be found. In some cases this can occur with bracket orders if the child order is placed immediately after the parent order; a brief pause of 50 ms or less will be necessary before the child order is transmitted to TWS/IBG.                                                                                                                                                                      |

| 10007          | Invalid hedge type.                                                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10008          | Invalid beta value.                                                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10009          | Invalid hedge ratio.                                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10010          | Invalid delta hedge order.                                                                                                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10011          | Currency is not supported for Smart combo.                                                                                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10012          | Invalid allocation percentage                                                                                                                                                                                                                                                   | FaPercentage specified is not valid                                                                                                                                                                                                                                                                                                                                                                                                      |

| 10013          | Smart routing API error (Smart routing opt-out required).                                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10014          | PctChange limits.                                                                                                                                                                                                                                                               | This error is deprecated                                                                                                                                                                                                                                                                                                                                                                                                                 |

| 10015          | Trading is not allowed in the API.                                                                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10016          | Contract is not visible.                                                                                                                                                                                                                                                        | This error is deprecated                                                                                                                                                                                                                                                                                                                                                                                                                 |

| 10017          | Contracts are not visible.                                                                                                                                                                                                                                                      | This error is deprecated                                                                                                                                                                                                                                                                                                                                                                                                                 |

| 10018          | Orders use EV warning.                                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10019          | Trades use EV warning.                                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10020          | Display size should be smaller than order size./td\>                                                                                                                                                                                                                             | The display size should be smaller than the total quantity                                                                                                                                                                                                                                                                                                                                                                               |

| 10021          | Invalid leg2 to Mkt Offset API.                                                                                                                                                                                                                                                 | This error is deprecated                                                                                                                                                                                                                                                                                                                                                                                                                 |

| 10022          | Invalid Leg Prio API.                                                                                                                                                                                                                                                           | This error is deprecated                                                                                                                                                                                                                                                                                                                                                                                                                 |

| 10023          | Invalid combo display size API.                                                                                                                                                                                                                                                 | This error is deprecated                                                                                                                                                                                                                                                                                                                                                                                                                 |

| 10024          | Invalid don't start next legin API.                                                                                                                                                                                                                                             | This error is deprecated                                                                                                                                                                                                                                                                                                                                                                                                                 |

| 10025          | Invalid leg2 to Mkt time1 API.                                                                                                                                                                                                                                                  | This error is deprecated                                                                                                                                                                                                                                                                                                                                                                                                                 |

| 10026          | Invalid leg2 to Mkt time2 API.                                                                                                                                                                                                                                                  | This error is deprecated                                                                                                                                                                                                                                                                                                                                                                                                                 |

| 10027          | Invalid combo routing tag API.                                                                                                                                                                                                                                                  | This error is deprecated                                                                                                                                                                                                                                                                                                                                                                                                                 |

| 10089          | API data requires subscription                                                                                                                                                                                                                                                  | The market data subscribed with the user does not extend support for API use. See \[TWS vs API Data\](/general/market-data-subscriptions/tws-data-vs-api-data) for more details.                                                                                                                                                                                                                                                           |

| 10090          | Part of requested market data is not subscribed.                                                                                                                                                                                                                                | Indicates that some tick types requested require additional market data subscriptions not held in the account. This commonly occurs for instance if a user has options subscriptions but not the underlying stock so the system cannot calculate the real time Greek values (other default ticks will be returned). Or alternatively, if generic tick types are specified in a market data request without the associated subscriptions. |

| 10091          | Part of requested market data requires additional subscription for API                                                                                                                                                                                                          | The market data subscribed with the user does not extend support for API use. See \[TWS vs API Data\](/general/market-data-subscriptions/tws-data-vs-api-data) for more details.                                                                                                                                                                                                                                                           |

| 10147          | Order to be canceled was not found.                                                                                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10148          | "OrderId that needs to be cancelled can not be cancelled, state:"                                                                                                                                                                                                               | An attempt was made to cancel an order that had already been filled by the system.                                                                                                                                                                                                                                                                                                                                                       |

| 10186          | Requested market data is not subscribed. Delayed market data is not enabled                                                                                                                                                                                                     | See Market Data Types on how to enable delayed data.                                                                                                                                                                                                                                                                                                                                                                                     |

| 10187          | Failed to request historical ticks:No market data permissions                                                                                                                                                                                                                   |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10189          | Failed to request tick-by-tick data. Invalid Real-time Query                                                                                                                                                                                                                    | "Trading TWS session is connected from a different IP address. Or, No market data permissions"                                                                                                                                                                                                                                                                                                                                           |

| 10197          | No market data during competing session                                                                                                                                                                                                                                         | "Indicates that the user is logged into the paper account and live account simultaneously trying to request live market data using both the accounts. In such a scenario preference would be given to the live account, for more details please refer: \[https://ibkr.info/node/1719\](https://ibkr.info/node/1719)"                                                                                                                       |

| 10225          | "Bust event occurred, current subscription is deactivated. Please resubscribe real-time bars immediately"                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10230          | "You have unsaved FA changes. Please retry 'request FA' operation later, when 'replace FA' operation is complete"                                                                                                                                                               | There are pending Financial Advisor configuration changes. See Financial Advisors                                                                                                                                                                                                                                                                                                                                                        |

| 10231          | The following Groups and/or Profiles contain invalid accounts:                                                                                                                                                                                                                  | "If the account(s) inside Groups or Profiles is/are incorrect in xml-formatted configuration string of replaceFA request, then the error shows list of such Groups and/or Profiles."                                                                                                                                                                                                                                                     |

| 10233          | Defaults were inherited from CASH preset during the creation of this order.                                                                                                                                                                                                     |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10234          | The Decision Maker field is required and not set for this order (non-desktop).                                                                                                                                                                                                  |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10235          | The Decision Maker field is required and not set for this order (ibbot).                                                                                                                                                                                                        |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10236          | Child has to be AON if parent order is AON                                                                                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10237          | All or None ticket can route entire unfilled size only                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10238          | Some error occured during communication with Advisor Setup web-app                                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10239          | This order will affect one or more accounts that are flagged because they do not fit the required risk score criteria prescribed by the group/profile/model allocation.                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10240          | You must enter a valid Price Cap.                                                                                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10241          | Order Quantity is expressed in monetary terms. Modification is not supported via API. Please use desktop version to revise this order.                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10242          | Fractional-sized order cannot be modified via API. Please use desktop version to revise this order.                                                                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10243          | Fractional-sized order cannot be placed via API. Please use desktop version to place this order.                                                                                                                                                                                |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10244          | Cash Quantity cannot be used for this order                                                                                                                                                                                                                                     |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10245          | This financial instrument does not support fractional shares trading                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10246          | This order doesn't support fractional shares trading                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10247          | Only IB SmartRouting supports fractional shares                                                                                                                                                                                                                                 |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10248          | doesn't have permission to trade fractional shares                                                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10249          | "=""\> order doesn't support fractional shares"                                                                                                                                                                                                                                  |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10250          | The size does not conform to the minimum variation of for this contract                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10251          | Fractional shares are not supported for allocation orders                                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10252          | This non-close-position order doesn't support fractional shares trading                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10253          | Clear Away orders are not supported for multi-leg combo with attached hedge.                                                                                                                                                                                                    |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10254          | Invalid Order: bond expired                                                                                                                                                                                                                                                     |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10268          | The 'EtradeOnly' order attribute is not supported                                                                                                                                                                                                                               | The EtradeOnly IBApi.Order attribute is no longer supported. Error received with TWS versions 983+                                                                                                                                                                                                                                                                                                                                       |

| 10269          | The 'firmQuoteOnly' order attribute is not supported                                                                                                                                                                                                                            | The firmQuoteOnly IBApi.Order attribute is no longer supported. Error received with TWS versions 983+                                                                                                                                                                                                                                                                                                                                    |

| 10270          | The 'nbboPriceCap' order attribute is not supported                                                                                                                                                                                                                             | The nbboPriceCap IBApi.Order attribute is no longer supported. Error received with TWS versions 983+                                                                                                                                                                                                                                                                                                                                     |

| 10276          | News feed is not allowed                                                                                                                                                                                                                                                        | The API client is not permissioned for receiving WSH news feed.                                                                                                                                                                                                                                                                                                                                                                          |

| 10277          | News feed permissions required                                                                                                                                                                                                                                                  | The API client is not subscribed to receive WSH news feed                                                                                                                                                                                                                                                                                                                                                                                |

| 10278          | Duplicate WSH metadata request                                                                                                                                                                                                                                                  | A request is already pending for the same API client.                                                                                                                                                                                                                                                                                                                                                                                    |

| 10279          | Failed request WSH metadata                                                                                                                                                                                                                                                     | A general error occurred when processing the request.                                                                                                                                                                                                                                                                                                                                                                                    |

| 10280          | Failed cancel WSH metadata                                                                                                                                                                                                                                                      | A general error occurred when processing the request.                                                                                                                                                                                                                                                                                                                                                                                    |

| 10281          | Duplicate WSH event data request                                                                                                                                                                                                                                                | A request is already pending for the same API client.                                                                                                                                                                                                                                                                                                                                                                                    |

| 10282          | WSH metadata not requested                                                                                                                                                                                                                                                      | WSH metadata was not requested by first sending a reqWshMetaData request.                                                                                                                                                                                                                                                                                                                                                                |

| 10283          | Fail request WSH event data                                                                                                                                                                                                                                                     | A general error occurred when processing the request.                                                                                                                                                                                                                                                                                                                                                                                    |

| 10284          | Fail cancel WSH event data                                                                                                                                                                                                                                                      | A general error occurred when processing the request.                                                                                                                                                                                                                                                                                                                                                                                    |

| 10285          | Your API version does not support fractional sizing rules. Please upgrade to at least version 163                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10286          | %s field cannot contain more than %s decimals.                                                                                                                                                                                                                                  |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10287          | Cryptocurrency order is not confirmed                                                                                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10288          | Market order confirmation dialog title for cryptocurrencies                                                                                                                                                                                                                     |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10289          | You must set Cash Quantity for this order                                                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10290          | This order only supports CashQty trading.                                                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10291          | Orders to harvest Capital Loss must use the DAY time-in-force.                                                                                                                                                                                                                  |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10292          | Order type/action restriction                                                                                                                                                                                                                                                   |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10293          | Cryptocurrency Cash Quantity order cannot specify size                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10294          | Cash quantity set on the order does not match total monetary amount of the Group.                                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10295          | Orders to harvest Capital Loss must use the DAY time-in-force.                                                                                                                                                                                                                  |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10295          | Only daily resolution supported for Schedule requests                                                                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10296          | "The Smart Routing features "Seek Price Improvement" (aka "Route to Dark Pools") and "Do not route to Dark Pools" are mutually exclusive. Enabling both will result in the order being rejected. Please choose only one of these commands.%s"                                   |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10297          | Not Held attribute is invalid for this order.                                                                                                                                                                                                                                   |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10298          | Cannot trade an instrument with currency different from model currency                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10299          | Expected what to show is %s                                                                                                                                                                                                                                                     | please use that instead of %s.                                                                                                                                                                                                                                                                                                                                                                                                           |

| 10300          | %s: The date                                                                                                                                                                                                                                                                    | time                                                                                                                                                                                                                                                                                                                                                                                                                                     |

| 10301          | %s: The date                                                                                                                                                                                                                                                                    | time                                                                                                                                                                                                                                                                                                                                                                                                                                     |

| 10302          | Min trade trade quantity is not allowed for this order                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10303          | Invalid min trade quantity value (%s). It must be a positive integer                                                                                                                                                                                                            | not exceeding the total order size.                                                                                                                                                                                                                                                                                                                                                                                                      |

| 10304          | Minimum Competing Size value must be non-negative.                                                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10305          | Compete against best bid or offer Offset dollar value must be positive                                                                                                                                                                                                          | multiple of a cent.                                                                                                                                                                                                                                                                                                                                                                                                                      |

| 10306          | Mid offsets are not allowed                                                                                                                                                                                                                                                     |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10307          | Invalid MidOffsetAtWhole and/or MidOffsetAtHalf attribute values                                                                                                                                                                                                                |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10308          | Revision to Post to ATS value presence is not allowed.                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10309          | Invalid WSH event data request.                                                                                                                                                                                                                                                 |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10310          | The Solicited field should be used for orders initiated or recommended by the broker or advisor that were approved by the client by phone or email.                                                                                                                             |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10311          | This order will be directly routed to %s. Direct routed orders may result in higher trade fees.                                                                                                                                                                                 |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10312          | The order type Volatility is currently not supported for this combination of financial instrument and account type                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10314          | %s: The date                                                                                                                                                                                                                                                                    | time                                                                                                                                                                                                                                                                                                                                                                                                                                     |

| 10315          | %s: The time entered is invalid. The correct format is hh:mm:ss. E.g.: 15:00:00 in UTC. No date should be specified                                                                                                                                                             | current date is assumed.                                                                                                                                                                                                                                                                                                                                                                                                                 |

| 10316          | Trigger Outside RTH was deprecated. Please upgrade your API Client software to submit order with Outside RTH attribute instead.                                                                                                                                                 |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10317          | The Cash Quantity size for the below contracts does not conform to minimum variation of %s                                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10318          | This order doesn't support fractional quantity trading                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10319          | Placing orders for Municipal Bonds via API is currently disabled                                                                                                                                                                                                                |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10321          | Placing orders for Municipal Bonds is currently disabled for attached and OCA orders.                                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10322          | This API request for All is not supported for Dynamic Account Addition                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10324          | Invalid parameters for OCA group for exchange %s. Overfill Protection is implied.                                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10325          | OCA group is not supported                                                                                                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10326          | OCA group revision is not allowed                                                                                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10327          | OCA group type revision is not allowed                                                                                                                                                                                                                                          |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10328          | Connection lost                                                                                                                                                                                                                                                                 | order data could not be resolved                                                                                                                                                                                                                                                                                                                                                                                                         |

| 10329          | This order will be directly routed to %s.                                                                                                                                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10330          | The expiry date/time format is invalid.\\nThe correct format is yyyyMMdd HH:mm:ss (operator or instrument time zone) or yyyyMMdd-HH:mm:ss (UTC time zone).                                                                                                                       |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10331          | Any stop warning                                                                                                                                                                                                                                                                |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10332          | Cryptocurrency volatility warning                                                                                                                                                                                                                                               |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10333          | Option Exercise at-the-money warning                                                                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10334          | Confirm Omnibus Order Account                                                                                                                                                                                                                                                   |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10335          | "Order presets cannot be applied as configured. Please review %s Settings and Rapid Order Entry Configuration for consistency."                                                                                                                                                 |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10336          | Per-leg executing broker configuration is not supported                                                                                                                                                                                                                         |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10337          | Misc options key=%s is invalid in %s request. Valid keys are: %s                                                                                                                                                                                                                |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10338          | Misc options value=%s is invalid for key=%s in %s request. Valid values are: %s                                                                                                                                                                                                 |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10339          | Setting end date/time for continuous future security type is not allowed                                                                                                                                                                                                        |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10340          | The following order attribute is not supported: %s                                                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10341          | Parent order id cannot be modified                                                                                                                                                                                                                                              |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10342          | The 'ImbalanceOnly' order attribute may not be specified for this order.                                                                                                                                                                                                        |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10343          | Selling Event Contracts is neither allowed directly nor as an attached profit taker.                                                                                                                                                                                            |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10344          | Price value must be between 0.02 and 0.99 with a maximum of two decimal places.                                                                                                                                                                                                 |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10345          | You cannot trade a %s                                                                                                                                                                                                                                                           |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10346          | Market data for %s cannot be delivered because ticker for the same financial instrument is displayed on %s                                                                                                                                                                      |                                                                                                                                                                                                                                                                                                                                                                                                                                          |

| 10347          | This security has limited liquidity. If you choose to trade this security                                                                                                                                                                                                       | there is a heightened risk that you may not be able to close your position  at the time you wish                                                                                                                                                                                                                                                                                                                                         |

| WinError 10038 | An operation was attempted on something that is not a socket.                                                                                                                                                                                                                   | This indicates socket connection was closed improperly.                                                                                                                                                                                                                                                                                                                                                                                  |

&nbsp;

&nbsp;

&nbsp;

&nbsp;

\---

&nbsp;

\#\# title: Receiving Error Messages

&nbsp;

\#\#\#\# EWrapper.error(

&nbsp;

\*\*reqId:\*\* int. The request identifier corresponding to the most recent reqId that maintained the error stream.\\

This does not pertain to the orderId from placeOrder, but whatever the most recent requestId is.

&nbsp;

\*\*errorTime:\*\* int. The Unix timestamp of when the error took place.\\

Note: This is only implemented for TWS API 10.33+

&nbsp;

\*\*errorCode:\*\* int. The code identifying the error.

&nbsp;

\*\*errorMsg:\*\* String. The error's description.

&nbsp;

\*\*advancedOrderRejectJson:\*\* String. Advanced order reject description in json format.\\

)

&nbsp;

\<Tabs\>

  \<Tab title="Python" language="python"\>

    \`\`\`python

    def error(self, reqId: TickerId, errorTime: int, errorCode: int, errorString: str, advancedOrderRejectJson \= ""):

      print("Error. Id:", reqId, errorTime, "Code:", errorCode, "Msg:", errorString, "AdvancedOrderRejectJson:", advancedOrderRejectJson)

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="Java" language="java"\>

    \`\`\`java

    @Override

    public void error(int id, long errorTime, int errorCode, String errorMsg, String advancedOrderRejectJson) {

      String str \= "Error. Id: " \+ id \+ ", Code: " \+ errorCode \+ ", Msg: " \+ errorMsg;

      if (advancedOrderRejectJson \!= null) {

        str \+= (", AdvancedOrderRejectJson: " \+ advancedOrderRejectJson);

      }

      System.out.println(str \+ "\\n");

    }

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="C++" language="cpp"\>

    \`\`\`cpp

    void TestCppClient::error(int id, time\_t errorTime, int errorCode, const std::string& errorString, const std::string& advancedOrderRejectJson)

    {

        printf("Error. Id: %d, Timestamp: %d, Code: %d, Msg: %s, AdvancedOrderRejectJson: %s\\n", id, errorTime, errorCode, errorString.c\_str(), advancedOrderRejectJson.c\_str());

    }

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="C\#" language="csharp"\>

    \`\`\`csharp

    public virtual void error(int id, long errorTime, int errorCode, string errorMsg, string advancedOrderRejectJson)

    {

      Console.WriteLine("Error. Id: " \+ id \+ "Timestamp: " \+ errorTime \+ ", Code: " \+ errorCode \+ ", Msg: " \+ errorMsg \+ ", AdvancedOrderRejectJson: " \+ advancedOrderRejectJson \+ "\\n");

    }

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="VB.NET" language="vbnet"\>

    \`\`\`vbnet

    Public Sub \[error\](id As Integer, errorCode As Integer, errorMsg As String, advancedOrderRejectJson As String) Implements IBApi.EWrapper.error

                Console.WriteLine("Error \- Id \[" & id & "\] ErrorCode \[" & errorCode & "\] ErrorMsg \[" & errorMsg & "\] AdvancedOrderRejectJson \[" & advancedOrderRejectJson & "\]")

    End Sub

    \`\`\`

  \</Tab\>

\</Tabs\>

&nbsp;

&nbsp;

&nbsp;

&nbsp;

&nbsp;

&nbsp;

MARKET DATA HISTORICAL

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Historical Market data is available for Interactive Brokers market data subscribers in a range of methods and structures. This includes requests for historical bars, identical to the Trader Workstation, historical Time & Sales, as well as Histogram data.

&nbsp;

Historical Data Limitations

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Historical market data has it's own set of market data limitations unique to other requests such as real time market data. This section will cover all limitations that effect historical market data in the Trader Workstation API.

&nbsp;

\---

&nbsp;

\#\# title: Historical Data Filtering

&nbsp;

Historical data at IB is filtered for trade types which occur away from the NBBO such as combo legs, block trades, and derivative trades. For that reason the daily volume from the (unfiltered) real time data functionality will generally be larger than the (filtered) historical volume reported by historical data functionality. Also, differences are expected in other fields such as the VWAP between the real time and historical data feeds.

&nbsp;

As historical data at IB gets adjusted, compressed and filtered by default, there may be historical data differences if you request historical data at different time points.

&nbsp;

See our FAQ for more insight, \[here\](https://www.interactivebrokers.com/lib/cstools/faq/\#/content/102546341).

&nbsp;

\---

&nbsp;

\#\# title: Historical Volume Scaling

&nbsp;

Volume data returned for historical bars can be modified to return in shares or lots.

&nbsp;

1\. Open the Global Configuration window

2\. Navigate to "API" and then "Settings" on the left pane

3\. Scroll down to the "Send market data in lots for US Stocks for dual-mode API clients"

&nbsp;

If the setting is checked, historical volume data will return as a \[Round Lot\](https://www.investopedia.com/terms/r/roundlot.asp).

&nbsp;

If the setting is unchecked, historical volume data will return in Shares.

&nbsp;

\!\[Send market data in lots for US stocks for dual-mode API clients highlighted in API Settings.\](file:docs/assets/media/hist\_volume\_modifier.png)

&nbsp;

\---

&nbsp;

\#\# title: Pacing Violations for Small Bars (30 secs or less)

&nbsp;

Although Interactive Brokers offers our clients high quality market data, IB is not a specialised market data provider and as such it is forced to put in place restrictions to limit traffic which is not directly associated to trading. A Pacing Violation occurs whenever one or more of the following restrictions is not observed:

&nbsp;

Important: these limitations apply to all our clients and it is not possible to overcome them. If your trading strategy's market data requirements are not met by our market data services please consider contacting a specialized provider.

&nbsp;

\* Making identical historical data requests within 15 seconds.

\* Making six or more historical data requests for the same Contract, Exchange and Tick Type within two seconds.

\* Making more than 60 requests within any ten minute period.

\* Note that when BID\\\_ASK historical data is requested, each request is counted twice. In a nutshell, the information above can simply be put as "do not request too much data too quick".

&nbsp;

\---

&nbsp;

\#\# title: Unavailable Historical Data

&nbsp;

The other historical data limitations listed are general limitations for all trading platforms:

&nbsp;

\* Bars whose size is 30 seconds or less older than six months

\* Expired futures data older than two years counting from the future's expiration date.

\* Expired options, FOPs, warrants and structured products.

\* End of Day (EOD) data for options, FOPs, warrants and structured products.

\* Data for expired future spreads

\* Data for securities which are no longer trading.

\* Native historical data for combos. Historical data is not stored in the IB database separately for combos.; combo historical data in TWS or the API is the sum of data from the legs.

\* Historical data for securities which move to a new exchange will often not be available prior to the time of the move. For example, SOXX stock moved to NASDAQ exchange on 15 Oct 2010, so no SOXX data before 15 Oct 2010 can be retrieved despite SOXX was listed in 2001\. This limitation also applied to contract which specifies \`SMART\` as the exchange.

\* Studies and indicators such as Weighted Moving Averages or Bollinger Bands are not available from the API.

\* Time & Sales data beyond 3 years.

&nbsp;

Finding the Earliest Available Data Point

\---

&nbsp;

\#\# title: Introduction

&nbsp;

For many functions, such as EClient.reqHistoricalData, you will need to request market data for a contract. Given that you may not know how long a symbol has been available, you can use EClient.reqHeadTimestamp to find the first available point of data for a given whatToShow value.

&nbsp;

ReqHeadTimeStamp counts as an ongoing historical data request, similar to using EClient.reqHistoricalData's keepUpToDate=True flag. As a result, users should always:

&nbsp;

\* Cancel timestamp requests using \[EClient.cancelHeadTimeStamp\](/tws-api/doc/market-data-historical/finding-the-earliest-available-data-point/cancelling-timestamp-requests).

\* All EClient.reqHeadTimestamp requests follow the \[30 second bar limitations\](/tws-api/doc/market-data-historical/historical-data-limitations/introduction), regardless of which bar size value has been requested.

&nbsp;

\---

&nbsp;

\#\# title: Requesting the Earliest Data Point

&nbsp;

\#\#\#\# EClient.reqHeadTimestamp (

&nbsp;

\*\*tickerId:\*\* int., A unique identifier which will serve to identify the incoming data.

&nbsp;

\*\*contract:\*\* Contract\\\*\\\*.\\\*\\\* The IBApi.Contract you are interested in.

&nbsp;

\*\*whatToShow:\*\* String. The type of data to retrieve. See Historical Data Types

&nbsp;

\*\*useRTH:\*\* int. Whether (1) or not (0) to retrieve data generated only within Regular Trading Hours (RTH)

&nbsp;

\*\*formatDate:\*\* int. Using 1 will return UTC time in YYYYMMDD-hh:mm:ss format. Using 2 will return epoch time.\\

)

&nbsp;

Returns the timestamp of earliest available historical data for a contract and data type.

&nbsp;

\<Tabs\>

  \<Tab title="Python" language="python"\>

    \`\`\`python

    self.reqHeadTimeStamp(1, ContractSamples.USStockAtSmart(), "TRADES", 1, 1\)

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="Java" language="java"\>

    \`\`\`java

    client.reqHeadTimestamp(4003, contract, "TRADES", 1, 1);

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="C++" language="cpp"\>

    \`\`\`cpp

    m\_pClient-\>reqHeadTimestamp(14001, contract, "MIDPOINT", 1, 1);

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="C\#" language="csharp"\>

    \`\`\`csharp

    client.reqHeadTimestamp(14001, contract, "TRADES", 1, 1);

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="VB.NET" language="vbnet"\>

    \`\`\`vbnet

    client.reqHeadTimestamp(14001, ContractSamples.USStock(), "TRADES", 1, 1\)

    \`\`\`

  \</Tab\>

\</Tabs\>

&nbsp;

\---

&nbsp;

\#\# title: Receiving the Earliest Data Point

&nbsp;

\#\#\#\# EWrapper.headTimestamp (

&nbsp;

\*\*requestId:\*\* int. Request identifier used to track data.

&nbsp;

\*\*headTimestamp:\*\* String. Value identifying earliest data date\\

)

&nbsp;

The data requested will be returned to EWrapper.headTimeStamp.

&nbsp;

\<Tabs\>

  \<Tab title="Python" language="python"\>

    \`\`\`python

    def headTimestamp(self, reqId, headTimestamp):

            print(reqId, headTimestamp)

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="Java" language="java"\>

    \`\`\`java

    @Override

    public void headTimestamp(int reqId, String headTimestamp) {

    	System.out.println(EWrapperMsgGenerator.headTimestamp(reqId, headTimestamp));

    }

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="C++" language="cpp"\>

    \`\`\`cpp

    void TestCppClient::headTimestamp(int reqId, const std::string& headTimestamp) {

        printf( "Head time stamp. ReqId: %d \- Head time stamp: %s,\\n", reqId, headTimestamp.c\_str());

    }

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="C\#" language="csharp"\>

    \`\`\`csharp

    public void headTimestamp(int reqId, string headTimestamp)

    {

    	Console.WriteLine("Head time stamp. Request Id: {0}, Head time stamp: {1}", reqId, headTimestamp);

    }

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="VB.NET" language="vbnet"\>

    \`\`\`vbnet

    Public Sub headTimestamp(requestId As Integer, timeStamp As String) Implements IBApi.EWrapper.headTimestamp

    	Console.WriteLine("Head time stamp. Request Id: {0}, Head time stamp: {1}", requestId, timeStamp)

    End Sub

    \`\`\`

  \</Tab\>

\</Tabs\>

&nbsp;

\---

&nbsp;

\#\# title: Cancelling Timestamp Requests

&nbsp;

\#\#\#\# EWrapper.cancelHeadTimeStamp (

&nbsp;

\*\*tickerId:\*\* int. Request identifier used to track data.\\

)

&nbsp;

A reqHeadTimeStamp request can be cancelled with EClient.cancelHeadTimestamp

&nbsp;

\<Tabs\>

  \<Tab title="Python" language="python"\>

    \`\`\`python

    self.cancelHeadTimeStamp(reqId)

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="Java" language="java"\>

    \`\`\`java

    client.cancelHeadTimestamp(4003);

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="C++" language="cpp"\>

    \`\`\`cpp

    m\_pClient-\>cancelHeadTimestamp(14001);

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="C\#" language="csharp"\>

    \`\`\`csharp

    client.cancelHeadTimestamp(14001);

    \`\`\`

  \</Tab\>

&nbsp;

  \<Tab title="VB.NET" language="vbnet"\>

    \`\`\`vbnet

    client.cancelHeadTimestamp(14001)

    \`\`\`

  \</Tab\>

\</Tabs\>

&nbsp;

&nbsp;

TWS DOCUMENTATION

\---

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Class describing an order's execution.

&nbsp;

| Name                 | Type      | Description                                                                                                                                                                                                  |

| \-------------------- | \--------- | \------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |

| OrderId              | int       | The API client's order Id. May not be unique to an account.                                                                                                                                                  |

| ClientId             | int       | The API client identifier which placed the order which originated this execution.                                                                                                                            |

| ExecId               | string    | The execution's identifier. Each partial fill has a separate ExecId. A correction is indicated by an ExecId which differs from a previous ExecId in only the digits after the final period                   |

| Time                 | string    | The execution's server time.                                                                                                                                                                                 |

| AcctNumber           | string    | The account to which the order was allocated.                                                                                                                                                                |

| Exchange             | string    | The exchange where the execution took place.                                                                                                                                                                 |

| Side                 | string    | Specifies if the transaction was buy or sale BOT for bought                                                                                                                                                  |

| Shares               | decimal   | The number of shares filled.                                                                                                                                                                                 |

| Price                | double    | The order's execution price excluding commissions.                                                                                                                                                           |

| PermId               | int       | The TWS order identifier. The PermId can be 0 for trades originating outside IB.                                                                                                                             |

| Liquidation          | int       | Identifies whether an execution occurred because of an IB-initiated liquidation.                                                                                                                             |

| CumQty               | decimal   | Cumulative quantity. Used in regular trades                                                                                                                                                                  |

| AvgPrice             | double    | Average price. Used in regular trades                                                                                                                                                                        |

| OrderRef             | string    | The OrderRef is a user-customizable string that can be set from the API or TWS and will be associated with an order for its lifetime.                                                                        |

| EvRule               | string    | The Economic Value Rule name and the respective optional argument. The two values should be separated by a colon. For example                                                                                |

| EvMultiplier         | double    | Tells you approximately how much the market value of a contract would change if the price were to change by 1\. It cannot be used to get market value by multiplying the price by the approximate multiplier. |

| ModelCode            | string    | model code                                                                                                                                                                                                   |

| LastLiquidity        | Liquidity | The liquidity type of the execution. Requires TWS 968+ and API v973.05+. Python API specifically requires API v973.06+.                                                                                      |

| PendingPriceRevision | bool      | pending price revision                                                                                                                                                                                       |

&nbsp;

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                | Type          | Description |

| \------------------- | \------------- | \----------- |

| Equals (object obj) | override bool |             |

| GetHashCode ()      | override int  |             |

&nbsp;

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Class describing an order's execution.

&nbsp;

| Name                 | Type      | Description                                                                                                                                                                                                  |

| \-------------------- | \--------- | \------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |

| OrderId              | int       | The API client's order Id. May not be unique to an account.                                                                                                                                                  |

| ClientId             | int       | The API client identifier which placed the order which originated this execution.                                                                                                                            |

| ExecId               | string    | The execution's identifier. Each partial fill has a separate ExecId. A correction is indicated by an ExecId which differs from a previous ExecId in only the digits after the final period                   |

| Time                 | string    | The execution's server time.                                                                                                                                                                                 |

| AcctNumber           | string    | The account to which the order was allocated.                                                                                                                                                                |

| Exchange             | string    | The exchange where the execution took place.                                                                                                                                                                 |

| Side                 | string    | Specifies if the transaction was buy or sale BOT for bought                                                                                                                                                  |

| Shares               | decimal   | The number of shares filled.                                                                                                                                                                                 |

| Price                | double    | The order's execution price excluding commissions.                                                                                                                                                           |

| PermId               | int       | The TWS order identifier. The PermId can be 0 for trades originating outside IB.                                                                                                                             |

| Liquidation          | int       | Identifies whether an execution occurred because of an IB-initiated liquidation.                                                                                                                             |

| CumQty               | decimal   | Cumulative quantity. Used in regular trades                                                                                                                                                                  |

| AvgPrice             | double    | Average price. Used in regular trades                                                                                                                                                                        |

| OrderRef             | string    | The OrderRef is a user-customizable string that can be set from the API or TWS and will be associated with an order for its lifetime.                                                                        |

| EvRule               | string    | The Economic Value Rule name and the respective optional argument. The two values should be separated by a colon. For example                                                                                |

| EvMultiplier         | double    | Tells you approximately how much the market value of a contract would change if the price were to change by 1\. It cannot be used to get market value by multiplying the price by the approximate multiplier. |

| ModelCode            | string    | model code                                                                                                                                                                                                   |

| LastLiquidity        | Liquidity | The liquidity type of the execution. Requires TWS 968+ and API v973.05+. Python API specifically requires API v973.06+.                                                                                      |

| PendingPriceRevision | bool      | pending price revision                                                                                                                                                                                       |

&nbsp;

\---

&nbsp;

\#\# title: Static Public Member Functions

&nbsp;

| Name          | Type          | Description      |

| \------------- | \------------- | \---------------- |

| GetAllTags () | static string | Returns All Tags |

&nbsp;

\---

&nbsp;

\#\# title: Bar Class Reference

&nbsp;

The historical data bar's description.

&nbsp;

| Name   | Type    | Description                                                                                                                                                          |

| \------ | \------- | \-------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| Time   | string  | The bar's date and time (either as a yyyymmss hh:mm:ss formatted string or as system time according to the request). Time zone is the TWS time zone chosen on login. |

| Open   | double  | The bar's open price.                                                                                                                                                |

| High   | double  | The bar's high price.                                                                                                                                                |

| Low    | double  | The bar's low price.                                                                                                                                                 |

| Close  | double  | The bar's close price.                                                                                                                                               |

| Volume | decimal | The bar's traded volume if available (only available for TRADES)                                                                                                     |

| Count  | int     | The number of trades during the bar's timespan (only available for TRADES)                                                                                           |

| WAP    | decimal | The bar's Weighted Average Price (only available for TRADES)                                                                                                         |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Class representing a leg within combo orders.

&nbsp;

| Name               | Type   | Description                                                                                                                                                                                                                                                                                                                                                                    |

| \------------------ | \------ | \------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |

| ConId              | int    | The Contract's IB's unique id.                                                                                                                                                                                                                                                                                                                                                 |

| Ratio              | int    | Select the relative number of contracts for the leg you are constructing. To help determine the ratio for a specific combination order                                                                                                                                                                                                                                         |

| Action             | string | The side (buy or sell) of the leg:  For individual accounts, only BUY and SELL are available. SSHORT is for institutions.                                                                                                                                                                                                                                                      |

| Exchange           | string | The destination exchange to which the order will be routed.                                                                                                                                                                                                                                                                                                                    |

| OpenClose          | int    | Specifies whether an order is an open or closing order. For institutional customers to determine if this order is to open or close a position. 0 – Same as the parent security. This is the only option for retail customers.  1 – Open. This value is only valid for institutional customers.  2 – Close. This value is only valid for institutional customers.  3 – Unknown. |

| ShortSaleSlot      | int    | For stock legs when doing short selling. Set to 1 \= clearing broker, 2 \= third party                                                                                                                                                                                                                                                                                           |

| DesignatedLocation | string | When ShortSaleSlot is 2, this field shall contain the designated location.                                                                                                                                                                                                                                                                                                     |

| ExemptCode         | int    | Mark order as exempt from short sale uptick rule.  Possible values:  0 – Does not apply the rule.  \-1 – Applies the short sale uptick rule.                                                                                                                                                                                                                                    |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name        | Type       | Description                                                                |

| \----------- | \---------- | \-------------------------------------------------------------------------- |

| SAME \= 0    | static int | Same as the parent security. This is the only option for retail customers. |

| OPEN \= 1    | static int | Open. This value is only valid for institutional customers.                |

| CLOSE \= 2   | static int | Close. This value is only valid for institutional customers.               |

| UNKNOWN \= 3 | static int | Unknown                                                                    |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Class representing the commissions and fees generated by an execution.

&nbsp;

| Name                | Type   | Description                                               |

| \------------------- | \------ | \--------------------------------------------------------- |

| ExecId              | string | the execution's id this commission belongs to.            |

| CommissionAndFees   | double | the combined cost of commissions and fees.                |

| Currency            | string | The currency denoting the value of the commissionAndFees. |

| RealizedPNL         | double | the realized profit and loss                              |

| Yield               | double | The income return.                                        |

| YieldRedemptionDate | int    | date expressed in yyyymmdd format.                        |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                | Type          | Description |

| \------------------- | \------------- | \----------- |

| Equals (object obj) | override bool |             |

| GetHashCode ()      | override int  |             |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Class describing an instrument's definition.

&nbsp;

| Name                         | Type                 | Description                                                                                                                                                                                                                                                                           |

| \---------------------------- | \-------------------- | \------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| ConId                        | int                  | The unique IB contract identifier.                                                                                                                                                                                                                                                    |

| Symbol                       | string               | The underlying's asset symbol.                                                                                                                                                                                                                                                        |

| SecType                      | string               | The security's type: STK – stock (or ETF) OPT – option FUT – future IND – index FOP – futures option CASH – forex pair BAG – combo WAR – warrant BOND- bond CMDTY- commodity NEWS- news FUND- mutual fund.                                                                            |

| LastTradeDateOrContractMonth | string               | The contract's last trading day or contract month (for Options and Futures). Strings with format YYYYMM will be interpreted as the Contract Month whereas YYYYMMDD will be interpreted as Last Trading Day.                                                                           |

| LastTradeDate                | string               | The contract's last trading day.                                                                                                                                                                                                                                                      |

| Strike                       | double               | The option's strike price.                                                                                                                                                                                                                                                            |

| Right                        | string               | Either Put or Call (i.e. Options). Valid values are P, PUT, C, CALL.                                                                                                                                                                                                                  |

| Multiplier                   | string               | The instrument's multiplier (i.e. options, futures).                                                                                                                                                                                                                                  |

| Exchange                     | string               | The destination exchange.                                                                                                                                                                                                                                                             |

| Currency                     | string               | The underlying's currency.                                                                                                                                                                                                                                                            |

| LocalSymbol                  | string               | The contract's symbol within its primary exchange. For options, this will be the OCC symbol                                                                                                                                                                                           |

| PrimaryExch                  | string               | The contract's primary exchange. For smart routed contracts, used to define contract in case of ambiguity.Should be defined as native exchange of contract. For exchanges which contain a period in name, will only be part of exchange name prior to period, i.e. ENEXT for ENEXT.BE |

| TradingClass                 | string               | The trading class name for this contract. Available in TWS contract description window as well. For example, GBL Dec '13 future's trading class is "FGBL"                                                                                                                             |

| IncludeExpired               | bool                 | If set to true, contract details requests and historical data queries can be performed pertaining to expired futures contracts. Expired options or other instrument types are not available.                                                                                          |

| SecIdType                    | string               | Security's identifier when querying contract's details or placing orders ISIN – Example: Apple: US0378331005 CUSIP – Example: Apple: 037833100\.                                                                                                                                       |

| SecId                        | string               | Identifier of the security type. More…                                                                                                                                                                                                                                                |

| Description                  | string               | Description of the contract.                                                                                                                                                                                                                                                          |

| IssuerId                     | string               | IssuerId of the contract.                                                                                                                                                                                                                                                             |

| ComboLegsDescription         | string               | Description of the combo legs.                                                                                                                                                                                                                                                        |

| ComboLegs                    | List                 | The legs of a combined contract definition. More…                                                                                                                                                                                                                                     |

| DeltaNeutralContract         | DeltaNeutralContract | Delta and underlying price for Delta-Neutral combo orders. Underlying (STK or FUT)                                                                                                                                                                                                    |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name       | Type            | Description |

| \---------- | \--------------- | \----------- |

| ToString() | override string |             |

&nbsp;

\---

&nbsp;

\#\# title: ContractDetails Class Reference

&nbsp;

Extended contract details.

&nbsp;

| Name                            | Type                                                                                              | Description                                                                                                                                                                                                                                                                                                                                                                                   |

| \------------------------------- | \------------------------------------------------------------------------------------------------- | \--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| Contract                        | Contract                                                                                          | A fully-defined Contract object.                                                                                                                                                                                                                                                                                                                                                              |

| MarketName                      | string                                                                                            | The market name for this product.                                                                                                                                                                                                                                                                                                                                                             |

| MinTick                         | double                                                                                            | The minimum allowed price variation. Note that many securities vary their minimum tick size according to their price. This value will only show the smallest of the different minimum tick sizes regardless of the product's price. Full information about the minimum increment price structure can be obtained with the reqMarketRule function or the IB Contract and Security Search site. |

| PriceMagnifier                  | int                                                                                               | Allows execution and strike prices to be reported consistently with market data                                                                                                                                                                                                                                                                                                               |

| OrderTypes                      | string                                                                                            | Supported order types for this product.                                                                                                                                                                                                                                                                                                                                                       |

| ValidExchanges                  | string                                                                                            | Valid exchange fields when placing an order for this contract.                                                                                                                                                                                                                                                                                                                                |

| None                            | The list of exchanges will is provided in the same order as the corresponding MarketRuleIds list. | None                                                                                                                                                                                                                                                                                                                                                                                          |

| UnderConId                      | int                                                                                               | For derivatives                                                                                                                                                                                                                                                                                                                                                                               |

| LongName                        | string                                                                                            | Descriptive name of the product.                                                                                                                                                                                                                                                                                                                                                              |

| ContractMonth                   | string                                                                                            | Typically the contract month of the underlying for a Future contract.                                                                                                                                                                                                                                                                                                                         |

| Industry                        | string                                                                                            | The industry classification of the underlying/product. For example                                                                                                                                                                                                                                                                                                                            |

| Category                        | string                                                                                            | The industry category of the underlying. For example                                                                                                                                                                                                                                                                                                                                          |

| Subcategory                     | string                                                                                            | The industry subcategory of the underlying. For example                                                                                                                                                                                                                                                                                                                                       |

| TimeZoneId                      | string                                                                                            | The time zone for the trading hours of the product. For example                                                                                                                                                                                                                                                                                                                               |

| TradingHours                    | string                                                                                            | The trading hours of the product. This value will contain the trading hours of the current day as well as the next's. For example                                                                                                                                                                                                                                                             |

| LiquidHours                     | string                                                                                            | The liquid hours of the product. This value will contain the liquid hours (regular trading hours) of the contract on the specified exchange. Format for TWS versions until 969: 20090507:0700-1830                                                                                                                                                                                            |

| EvRule                          | string                                                                                            | Contains the Economic Value Rule name and the respective optional argument. The two values should be separated by a colon. For example                                                                                                                                                                                                                                                        |

| EvMultiplier                    | double                                                                                            | Tells you approximately how much the market value of a contract would change if the price were to change by 1\. It cannot be used to get market value by multiplying the price by the approximate multiplier.                                                                                                                                                                                  |

| AggGroup                        | int                                                                                               | Aggregated group Indicates the smart-routing group to which a contract belongs. contracts which cannot be smart-routed have aggGroup \= \-1.                                                                                                                                                                                                                                                    |

| SecIdList                       | List                                                                                              | A list of contract identifiers that the customer is allowed to view. CUSIP/ISIN/etc. For US stocks                                                                                                                                                                                                                                                                                            |

| UnderSymbol                     | string                                                                                            | For derivatives                                                                                                                                                                                                                                                                                                                                                                               |

| UnderSecType                    | string                                                                                            | For derivatives                                                                                                                                                                                                                                                                                                                                                                               |

| MarketRuleIds                   | string                                                                                            | The list of market rule IDs separated by comma Market rule IDs can be used to determine the minimum price increment at a given price.                                                                                                                                                                                                                                                         |

| RealExpirationDate              | string                                                                                            | Real expiration date. Requires TWS 968+ and API v973.04+. Python API specifically requires API v973.06+.                                                                                                                                                                                                                                                                                      |

| LastTradeTime                   | string                                                                                            | Last trade time.                                                                                                                                                                                                                                                                                                                                                                              |

| StockType                       | string                                                                                            | Stock type.                                                                                                                                                                                                                                                                                                                                                                                   |

| Cusip                           | string                                                                                            | The nine-character bond CUSIP. For Bonds only. Receiving CUSIPs requires a CUSIP market data subscription.                                                                                                                                                                                                                                                                                    |

| Ratings                         | string                                                                                            | Identifies the credit rating of the issuer. This field is not currently available from the TWS API. For Bonds only. A higher credit rating generally indicates a less risky investment. Bond ratings are from Moody's and S\\\&P respectively. Not currently implemented due to bond market data restrictions.                                                                                  |

| DescAppend                      | string                                                                                            | A description string containing further descriptive information about the bond. For Bonds only.                                                                                                                                                                                                                                                                                               |

| BondType                        | string                                                                                            | The type of bond                                                                                                                                                                                                                                                                                                                                                                              |

| CouponType                      | string                                                                                            | The type of bond coupon. This field is currently not available from the TWS API. For Bonds only.                                                                                                                                                                                                                                                                                              |

| Callable                        | bool                                                                                              | If true                                                                                                                                                                                                                                                                                                                                                                                       |

| Putable                         | bool                                                                                              | Values are True or False. If true                                                                                                                                                                                                                                                                                                                                                             |

| Coupon                          | double                                                                                            | The interest rate used to calculate the amount you will receive in interest payments over the course of the year. This field is currently not available from the TWS API. For Bonds only.                                                                                                                                                                                                     |

| Convertible                     | bool                                                                                              | Values are True or False. If true                                                                                                                                                                                                                                                                                                                                                             |

| Maturity                        | string                                                                                            | he date on which the issuer must repay the face value of the bond. This field is currently not available from the TWS API. For Bonds only. Not currently implemented due to bond market data restrictions.                                                                                                                                                                                    |

| IssueDate                       | string                                                                                            | The date the bond was issued. This field is currently not available from the TWS API. For Bonds only. Not currently implemented due to bond market data restrictions.                                                                                                                                                                                                                         |

| NextOptionDate                  | string                                                                                            | Only if bond has embedded options. This field is currently not available from the TWS API. Refers to callable bonds and puttable bonds. Available in TWS description window for bonds.                                                                                                                                                                                                        |

| NextOptionType                  | string                                                                                            | Type of embedded option. This field is currently not available from the TWS API. Only if bond has embedded options.                                                                                                                                                                                                                                                                           |

| NextOptionPartial               | bool                                                                                              | Only if bond has embedded options. This field is currently not available from the TWS API. For Bonds only.                                                                                                                                                                                                                                                                                    |

| Notes                           | string                                                                                            | If populated for the bond in IB's database. For Bonds only.                                                                                                                                                                                                                                                                                                                                   |

| MinSize                         | decimal                                                                                           | Order's minimal size.                                                                                                                                                                                                                                                                                                                                                                         |

| SizeIncrement                   | decimal                                                                                           | Order's size increment.                                                                                                                                                                                                                                                                                                                                                                       |

| SuggestedSizeIncrement          | decimal                                                                                           | Order's suggested size increment.                                                                                                                                                                                                                                                                                                                                                             |

| FundName                        | string                                                                                            | Fund's name.                                                                                                                                                                                                                                                                                                                                                                                  |

| FundFamily                      | string                                                                                            | Fund's family.                                                                                                                                                                                                                                                                                                                                                                                |

| FundType                        | string                                                                                            | Fund's type.                                                                                                                                                                                                                                                                                                                                                                                  |

| FundFrontLoad                   | string                                                                                            | Fund's front load.                                                                                                                                                                                                                                                                                                                                                                            |

| FundBackLoad                    | string                                                                                            | Fund's back load.                                                                                                                                                                                                                                                                                                                                                                             |

| FundBackLoadTimeInterval        | string                                                                                            | Fund's back load time interval.                                                                                                                                                                                                                                                                                                                                                               |

| FundManagementFee               | string                                                                                            | Fund's management fee.                                                                                                                                                                                                                                                                                                                                                                        |

| FundClosed                      | bool                                                                                              | Fund closed flag.                                                                                                                                                                                                                                                                                                                                                                             |

| FundClosedForNewInvestors       | bool                                                                                              | Fund closed for new investors flag.                                                                                                                                                                                                                                                                                                                                                           |

| FundClosedForNewMoney           | bool                                                                                              | Fund closed for new money flag.                                                                                                                                                                                                                                                                                                                                                               |

| FundNotifyAmount                | string                                                                                            | Fund's notify amount.                                                                                                                                                                                                                                                                                                                                                                         |

| FundMinimumInitialPurchase      | string                                                                                            | Fund's minimum initial purchase.                                                                                                                                                                                                                                                                                                                                                              |

| FundSubsequentMinimumPurchase   | string                                                                                            | Fund's subsequent minimum purchase.                                                                                                                                                                                                                                                                                                                                                           |

| FundBlueSkyStates               | string                                                                                            | Fund's blue sky states.                                                                                                                                                                                                                                                                                                                                                                       |

| FundBlueSkyTerritories          | string                                                                                            | Fund's blue sky territories.                                                                                                                                                                                                                                                                                                                                                                  |

| FundDistributionPolicyIndicator | FundDistributionPolicyIndicator                                                                   | Fund's distribution policy indicator.                                                                                                                                                                                                                                                                                                                                                         |

| FundAssetType                   | FundAssetType                                                                                     | Fund's asset type.                                                                                                                                                                                                                                                                                                                                                                            |

&nbsp;

\---

&nbsp;

\#\# title: CodeMsgPair Class Reference

&nbsp;

Associates error code and error message as a pair.

&nbsp;

| Name    | Type   | Description |

| \------- | \------ | \----------- |

| Code    | int    | None        |

| Message | string | None        |

\---

&nbsp;

\#\# title: DeltaNeutralContract Class Reference

&nbsp;

Delta-Neutral Contract.

&nbsp;

| Name  | Type   | Description                                                                                     |

| \----- | \------ | \----------------------------------------------------------------------------------------------- |

| ConId | int    | The unique contract identifier specifying the security. Used for Delta-Neutral Combo contracts. |

| Delta | double | The underlying stock or future delta. Used for Delta-Neutral Combo contracts.                   |

| Price | double | The price of the underlying. Used for Delta-Neutral Combo contracts.                            |

&nbsp;

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

TWS/Gateway client class This client class contains all the available methods to communicate with IB. Up to thirty-two clients can be connected to a single instance of the TWS/Gateway simultaneously. From herein, the TWS/Gateway will be referred to as the Host.

&nbsp;

| Name                 | Type   | Description |

| \-------------------- | \------ | \----------- |

| AllowRedirect        | bool   |             |

| ServerTime           | string |             |

| optionalCapabilities | string |             |

| AsyncEConnect        | bool   |             |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                                                                                                                                                               | Type                                                                                                                                                                                                                                                                                                           | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                       |

| \------------------------------------------------------------------------------------------------------------------------------------------------------------------ | \-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | \----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| SetConnectOptions (string connectOptions)                                                                                                                          | void                                                                                                                                                                                                                                                                                                           | Ignore. Used for IB's internal purposes.                                                                                                                                                                                                                                                                                                                                                                                                                          |

| DisableUseV100Plus ()                                                                                                                                              | void                                                                                                                                                                                                                                                                                                           | Allows to switch between different current (V100+) and previous connection mechanisms.                                                                                                                                                                                                                                                                                                                                                                            |

| IsConnected ()                                                                                                                                                     | bool                                                                                                                                                                                                                                                                                                           | Indicates whether the API-TWS connection has been closed. Note: This function is not automatically invoked and must be by the API client. More…                                                                                                                                                                                                                                                                                                                   |

| startApi ()                                                                                                                                                        | void                                                                                                                                                                                                                                                                                                           | Initiates the message exchange between the client application and the TWS/IB Gateway.                                                                                                                                                                                                                                                                                                                                                                             |

| Close ()                                                                                                                                                           | void                                                                                                                                                                                                                                                                                                           | Terminates the connection and notifies the EWrapper implementing class. More…                                                                                                                                                                                                                                                                                                                                                                                     |

| eDisconnect (bool resetState=true)                                                                                                                                 | virtual void                                                                                                                                                                                                                                                                                                   | Closes the socket connection and terminates its thread.                                                                                                                                                                                                                                                                                                                                                                                                           |

| reqCompletedOrders (bool apiOnly)                                                                                                                                  | void                                                                                                                                                                                                                                                                                                           | Requests completed orders.                                                                                                                                                                                                                                                                                                                                                                                                                                        |

| None                                                                                                                                                               | . More…                                                                                                                                                                                                                                                                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| cancelTickByTickData (int requestId)                                                                                                                               | void                                                                                                                                                                                                                                                                                                           | Cancels tick-by-tick data.                                                                                                                                                                                                                                                                                                                                                                                                                                        |

| None                                                                                                                                                               | . More…                                                                                                                                                                                                                                                                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| reqTickByTickData (int requestId                                                                                                                                   | void                                                                                                                                                                                                                                                                                                           | Contract contract                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

| None                                                                                                                                                               | . More…                                                                                                                                                                                                                                                                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| cancelHistoricalData (int reqId)                                                                                                                                   | void                                                                                                                                                                                                                                                                                                           | Cancels a historical data request. More…                                                                                                                                                                                                                                                                                                                                                                                                                          |

| calculateImpliedVolatility (int reqId                                                                                                                              | void                                                                                                                                                                                                                                                                                                           | Contract contract                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

| None                                                                                                                                                               | Request the calculation of the implied volatility based on hypothetical option and its underlying prices.                                                                                                                                                                                                      | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | The calculation will be return in EWrapper's tickOptionComputation callback.                                                                                                                                                                                                                                   | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | . More…                                                                                                                                                                                                                                                                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| calculateOptionPrice (int reqId                                                                                                                                    | void                                                                                                                                                                                                                                                                                                           | Contract contract                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

| None                                                                                                                                                               | The calculation will be return in EWrapper's tickOptionComputation callback.                                                                                                                                                                                                                                   | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | . More…                                                                                                                                                                                                                                                                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| cancelAccountSummary (int reqId)                                                                                                                                   | void                                                                                                                                                                                                                                                                                                           | Cancels the account's summary request. After requesting an account's summary                                                                                                                                                                                                                                                                                                                                                                                      |

| cancelCalculateImpliedVolatility (int reqId)                                                                                                                       | void                                                                                                                                                                                                                                                                                                           | Cancels an option's implied volatility calculation request. More…                                                                                                                                                                                                                                                                                                                                                                                                 |

| cancelCalculateOptionPrice (int reqId)                                                                                                                             | void                                                                                                                                                                                                                                                                                                           | Cancels an option's price calculation request. More…                                                                                                                                                                                                                                                                                                                                                                                                              |

| cancelFundamentalData (int reqId)                                                                                                                                  | void                                                                                                                                                                                                                                                                                                           | Cancels Fundamental data request. More…                                                                                                                                                                                                                                                                                                                                                                                                                           |

| cancelMktData (int tickerId)                                                                                                                                       | void                                                                                                                                                                                                                                                                                                           | Cancels a RT Market Data request. More…                                                                                                                                                                                                                                                                                                                                                                                                                           |

| cancelMktDepth (int tickerId                                                                                                                                       | void                                                                                                                                                                                                                                                                                                           | bool isSmartDepth)                                                                                                                                                                                                                                                                                                                                                                                                                                                |

| cancelNewsBulletin ()                                                                                                                                              | void                                                                                                                                                                                                                                                                                                           | Cancels IB's news bulletin subscription. More…                                                                                                                                                                                                                                                                                                                                                                                                                    |

| cancelOrder (int orderId                                                                                                                                           | void                                                                                                                                                                                                                                                                                                           | string manualOrderCancelTime)                                                                                                                                                                                                                                                                                                                                                                                                                                     |

| None                                                                                                                                                               | Note: API clients cannot cancel individual orders placed by other clients. Only reqGlobalCancel is available.                                                                                                                                                                                                  | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | . More…                                                                                                                                                                                                                                                                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| cancelPositions ()                                                                                                                                                 | void                                                                                                                                                                                                                                                                                                           | Cancels a previous position subscription request made with reqPositions. More…                                                                                                                                                                                                                                                                                                                                                                                    |

| cancelRealTimeBars (int tickerId)                                                                                                                                  | void                                                                                                                                                                                                                                                                                                           | Cancels Real Time Bars' subscription. More…                                                                                                                                                                                                                                                                                                                                                                                                                       |

| cancelScannerSubscription (int tickerId)                                                                                                                           | void                                                                                                                                                                                                                                                                                                           | Cancels Scanner Subscription. More…                                                                                                                                                                                                                                                                                                                                                                                                                               |

| exerciseOptions (int tickerId                                                                                                                                      | void                                                                                                                                                                                                                                                                                                           | Contract contract                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

| None                                                                                                                                                               | Note: this function is affected by a TWS setting which specifies if an exercise request must be finalized. More…                                                                                                                                                                                               | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| placeOrder (int id                                                                                                                                                 | void                                                                                                                                                                                                                                                                                                           | Contract contract                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

| replaceFA (int reqId                                                                                                                                               | void                                                                                                                                                                                                                                                                                                           | int faDataType                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

| requestFA (int faDataType)                                                                                                                                         | void                                                                                                                                                                                                                                                                                                           | Requests the FA configuration A Financial Advisor can define three different configurations: More…                                                                                                                                                                                                                                                                                                                                                                |

| reqAccountSummary (int reqId                                                                                                                                       | void                                                                                                                                                                                                                                                                                                           | string group                                                                                                                                                                                                                                                                                                                                                                                                                                                      |

| None                                                                                                                                                               | This method will subscribe to the account summary as presented in the TWS' Account Summary tab. The data is returned at EWrapper::accountSummary                                                                                                                                                               | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | \[https://www.interactivebrokers.com/en/software/tws/accountwindowtop.htm\](https://www.interactivebrokers.com/en/software/tws/accountwindowtop.htm). More…                                                                                                                                                      | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| reqAccountUpdates (bool subscribe                                                                                                                                  | void                                                                                                                                                                                                                                                                                                           | string acctCode)                                                                                                                                                                                                                                                                                                                                                                                                                                                  |

| reqAllOpenOrders ()                                                                                                                                                | void                                                                                                                                                                                                                                                                                                           | Requests all current open orders in associated accounts at the current moment. The existing orders will be received via the openOrder and orderStatus events. Open orders are returned once; this function does not initiate a subscription. More…                                                                                                                                                                                                                |

| reqAutoOpenOrders (bool autoBind)                                                                                                                                  | void                                                                                                                                                                                                                                                                                                           | Requests status updates about future orders placed from TWS. Can only be used with client ID 0\. More…                                                                                                                                                                                                                                                                                                                                                             |

| reqContractDetails (int reqId                                                                                                                                      | void                                                                                                                                                                                                                                                                                                           | Contract contract)                                                                                                                                                                                                                                                                                                                                                                                                                                                |

| None                                                                                                                                                               | This method will provide all the contracts matching the contract provided. It can also be used to retrieve complete options and futures chains. This information will be returned at EWrapper:contractDetails. Though it is now (in API version \> 9.72.12) advised to use reqSecDefOptParams for that purpose. | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | . More…                                                                                                                                                                                                                                                                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| reqCurrentTime ()                                                                                                                                                  | void                                                                                                                                                                                                                                                                                                           | Requests TWS's current time. More…                                                                                                                                                                                                                                                                                                                                                                                                                                |

| reqExecutions (int reqId                                                                                                                                           | void                                                                                                                                                                                                                                                                                                           | ExecutionFilter filter)                                                                                                                                                                                                                                                                                                                                                                                                                                           |

| reqFundamentalData (int reqId                                                                                                                                      | void                                                                                                                                                                                                                                                                                                           | Contract contract                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

| reqGlobalCancel ()                                                                                                                                                 | void                                                                                                                                                                                                                                                                                                           | Cancels all active orders.                                                                                                                                                                                                                                                                                                                                                                                                                                        |

| None                                                                                                                                                               | This method will cancel ALL open orders including those placed directly from TWS. More…                                                                                                                                                                                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| reqHistoricalData (int tickerId                                                                                                                                    | void                                                                                                                                                                                                                                                                                                           | Contract contract                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

| reqIds (int numIds)                                                                                                                                                | void                                                                                                                                                                                                                                                                                                           | Requests the next valid order ID at the current moment. More…                                                                                                                                                                                                                                                                                                                                                                                                     |

| reqManagedAccts ()                                                                                                                                                 | void                                                                                                                                                                                                                                                                                                           | Requests the accounts to which the logged user has access to. More…                                                                                                                                                                                                                                                                                                                                                                                               |

| reqMktData (int tickerId                                                                                                                                           | void                                                                                                                                                                                                                                                                                                           | Contract contract                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

| reqMarketDataType (int marketDataType)                                                                                                                             | void                                                                                                                                                                                                                                                                                                           | Switches data type returned from reqMktData request to "frozen"                                                                                                                                                                                                                                                                                                                                                                                                   |

| None                                                                                                                                                               | The API can receive frozen market data from Trader Workstation. Frozen market data is the last data recorded in our system.                                                                                                                                                                                    | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| the API receives real-time market data. Invoking this function with argument 2 requests a switch to frozen data immediately or after the close.                    | During normal trading hours                                                                                                                                                                                                                                                                                    | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| the market data type will automatically switch back to real time if available. More…                                                                               | When the market reopens                                                                                                                                                                                                                                                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| reqMarketDepth (int tickerId                                                                                                                                       | void                                                                                                                                                                                                                                                                                                           | Contract contract                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

| commissions                                                                                                                                                        | This request must be direct-routed to an exchange and not smart-routed. The number of simultaneous market depth requests allowed in an account is calculated based on a formula that looks at an accounts equity                                                                                               | and quote booster packs. More…                                                                                                                                                                                                                                                                                                                                                                                                                                    |

| reqNewsBulletins (bool allMessages)                                                                                                                                | void                                                                                                                                                                                                                                                                                                           | Subscribes to IB's News Bulletins. More…                                                                                                                                                                                                                                                                                                                                                                                                                          |

| reqOpenOrders ()                                                                                                                                                   | void                                                                                                                                                                                                                                                                                                           | Requests all open orders places by this specific API client (identified by the API client id). For client ID 0                                                                                                                                                                                                                                                                                                                                                    |

| reqPositions ()                                                                                                                                                    | void                                                                                                                                                                                                                                                                                                           | Subscribes to position updates for all accessible accounts. All positions sent initially                                                                                                                                                                                                                                                                                                                                                                          |

| reqRealTimeBars (int tickerId                                                                                                                                      | void                                                                                                                                                                                                                                                                                                           | Contract contract                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

| only 5 seconds bars are provided. This request is subject to the same pacing as any historical data request: no more than 60 API queries in more than 600 seconds. | Currently                                                                                                                                                                                                                                                                                                      | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | Real time bars subscriptions are also included in the calculation of the number of Level 1 market data subscriptions allowed in an account. More…                                                                                                                                                              | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| reqScannerParameters ()                                                                                                                                            | void                                                                                                                                                                                                                                                                                                           | Requests an XML list of scanner parameters valid in TWS.                                                                                                                                                                                                                                                                                                                                                                                                          |

| None                                                                                                                                                               | Not all parameters are valid from API scanner. More…                                                                                                                                                                                                                                                           | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| reqScannerSubscription (int reqId                                                                                                                                  | void                                                                                                                                                                                                                                                                                                           | ScannerSubscription subscription                                                                                                                                                                                                                                                                                                                                                                                                                                  |

| reqScannerSubscription (int reqId                                                                                                                                  | void                                                                                                                                                                                                                                                                                                           | ScannerSubscription subscription                                                                                                                                                                                                                                                                                                                                                                                                                                  |

| setServerLogLevel (int logLevel)                                                                                                                                   | void                                                                                                                                                                                                                                                                                                           | Changes the TWS/GW log level. The default is 2 \= ERROR                                                                                                                                                                                                                                                                                                                                                                                                            |

| None                                                                                                                                                               | 5 \= DETAIL is required for capturing all API messages and troubleshooting API programs                                                                                                                                                                                                                         | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | Valid values are:                                                                                                                                                                                                                                                                                              | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | 1 \= SYSTEM                                                                                                                                                                                                                                                                                                     | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | 2 \= ERROR                                                                                                                                                                                                                                                                                                      | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | 3 \= WARNING                                                                                                                                                                                                                                                                                                    | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | 4 \= INFORMATION                                                                                                                                                                                                                                                                                                | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | 5 \= DETAIL                                                                                                                                                                                                                                                                                                     | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | .                                                                                                                                                                                                                                                                                                              | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| verifyRequest (string apiName                                                                                                                                      | void                                                                                                                                                                                                                                                                                                           | string apiVersion)                                                                                                                                                                                                                                                                                                                                                                                                                                                |

| verifyMessage (string apiData)                                                                                                                                     | void                                                                                                                                                                                                                                                                                                           | For IB's internal purpose. Allows to provide means of verification between the TWS and third party programs.                                                                                                                                                                                                                                                                                                                                                      |

| verifyAndAuthRequest (string apiName                                                                                                                               | void                                                                                                                                                                                                                                                                                                           | string apiVersion                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

| verifyAndAuthMessage (string apiData                                                                                                                               | void                                                                                                                                                                                                                                                                                                           | string xyzResponse)                                                                                                                                                                                                                                                                                                                                                                                                                                               |

| queryDisplayGroups (int requestId)                                                                                                                                 | void                                                                                                                                                                                                                                                                                                           | Requests all available Display Groups in TWS. More…                                                                                                                                                                                                                                                                                                                                                                                                               |

| subscribeToGroupEvents (int requestId                                                                                                                              | void                                                                                                                                                                                                                                                                                                           | int groupId)                                                                                                                                                                                                                                                                                                                                                                                                                                                      |

| updateDisplayGroup (int requestId                                                                                                                                  | void                                                                                                                                                                                                                                                                                                           | string contractInfo)                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| unsubscribeFromGroupEvents (int requestId)                                                                                                                         | void                                                                                                                                                                                                                                                                                                           | Cancels a TWS Window Group subscription.                                                                                                                                                                                                                                                                                                                                                                                                                          |

| reqPositionsMulti (int requestId                                                                                                                                   | void                                                                                                                                                                                                                                                                                                           | string account                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

| cancelPositionsMulti (int requestId)                                                                                                                               | void                                                                                                                                                                                                                                                                                                           | Cancels positions request for account and/or model. More…                                                                                                                                                                                                                                                                                                                                                                                                         |

| reqAccountUpdatesMulti (int requestId                                                                                                                              | void                                                                                                                                                                                                                                                                                                           | string account                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

| cancelAccountUpdatesMulti (int requestId)                                                                                                                          | void                                                                                                                                                                                                                                                                                                           | Cancels account updates request for account and/or model. More…                                                                                                                                                                                                                                                                                                                                                                                                   |

| reqSecDefOptParams (int reqId                                                                                                                                      | void                                                                                                                                                                                                                                                                                                           | string underlyingSymbol                                                                                                                                                                                                                                                                                                                                                                                                                                           |

| reqSoftDollarTiers (int reqId)                                                                                                                                     | void                                                                                                                                                                                                                                                                                                           | Requests pre-defined Soft Dollar Tiers. This is only supported for registered professional advisors and hedge and mutual funds who have configured Soft Dollar Tiers in Account Management. Refer to: \[https://www.interactivebrokers.com/en/software/am/am/manageaccount/requestsoftdollars.htm?Highlight=soft%20dollar%20tier\](https://www.interactivebrokers.com/en/software/am/am/manageaccount/requestsoftdollars.htm?Highlight=soft%20dollar%20tier). More… |

| reqFamilyCodes ()                                                                                                                                                  | void                                                                                                                                                                                                                                                                                                           | Requests family codes for an account                                                                                                                                                                                                                                                                                                                                                                                                                              |

| reqMatchingSymbols (int reqId                                                                                                                                      | void                                                                                                                                                                                                                                                                                                           | string pattern)                                                                                                                                                                                                                                                                                                                                                                                                                                                   |

| reqMktDepthExchanges ()                                                                                                                                            | void                                                                                                                                                                                                                                                                                                           | Requests venues for which market data is returned to updateMktDepthL2 (those with market makers) More…                                                                                                                                                                                                                                                                                                                                                            |

| reqSmartComponents (int reqId                                                                                                                                      | void                                                                                                                                                                                                                                                                                                           | string bboExchange)                                                                                                                                                                                                                                                                                                                                                                                                                                               |

| reqNewsProviders ()                                                                                                                                                | void                                                                                                                                                                                                                                                                                                           | Requests news providers which the user has subscribed to. More…                                                                                                                                                                                                                                                                                                                                                                                                   |

| reqNewsArticle (int requestId                                                                                                                                      | void                                                                                                                                                                                                                                                                                                           | string providerCode                                                                                                                                                                                                                                                                                                                                                                                                                                               |

| reqHistoricalNews (int requestId                                                                                                                                   | void                                                                                                                                                                                                                                                                                                           | int conId                                                                                                                                                                                                                                                                                                                                                                                                                                                         |

| reqHeadTimestamp (int tickerId                                                                                                                                     | void                                                                                                                                                                                                                                                                                                           | Contract contract                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

| cancelHeadTimestamp (int tickerId)                                                                                                                                 | void                                                                                                                                                                                                                                                                                                           | Cancels a pending reqHeadTimeStamp request                                                                                                                                                                                                                                                                                                                                                                                                                        |

| None                                                                                                                                                               | . More…                                                                                                                                                                                                                                                                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| reqHistogramData (int tickerId                                                                                                                                     | void                                                                                                                                                                                                                                                                                                           | Contract contract                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

| None                                                                                                                                                               | . More…                                                                                                                                                                                                                                                                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| cancelHistogramData (int tickerId)                                                                                                                                 | void                                                                                                                                                                                                                                                                                                           | Cancels an active data histogram request. More…                                                                                                                                                                                                                                                                                                                                                                                                                   |

| reqMarketRule (int marketRuleId)                                                                                                                                   | void                                                                                                                                                                                                                                                                                                           | Requests details about a given market rule                                                                                                                                                                                                                                                                                                                                                                                                                        |

| None                                                                                                                                                               | The market rule for an instrument on a particular exchange provides details about how the minimum price increment changes with price                                                                                                                                                                           | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | A list of market rule ids can be obtained by invoking reqContractDetails on a particular contract. The returned market rule ID list will provide the market rule ID for the instrument in the correspond valid exchange list in contractDetails.                                                               | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| None                                                                                                                                                               | . More…                                                                                                                                                                                                                                                                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| reqPnL (int reqId                                                                                                                                                  | void                                                                                                                                                                                                                                                                                                           | string account                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

| cancelPnL (int reqId)                                                                                                                                              | void                                                                                                                                                                                                                                                                                                           | cancels subscription for real time updated daily PnL params reqId                                                                                                                                                                                                                                                                                                                                                                                                 |

| reqPnLSingle (int reqId                                                                                                                                            | void                                                                                                                                                                                                                                                                                                           | string account                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

| cancelPnLSingle (int reqId)                                                                                                                                        | void                                                                                                                                                                                                                                                                                                           | Cancels real time subscription for a positions daily PnL information. More…                                                                                                                                                                                                                                                                                                                                                                                       |

| reqHistoricalTicks (int reqId                                                                                                                                      | void                                                                                                                                                                                                                                                                                                           | Contract contract                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

| reqWshMetaData (int reqId)                                                                                                                                         | void                                                                                                                                                                                                                                                                                                           | Requests metadata from the WSH calendar. More…                                                                                                                                                                                                                                                                                                                                                                                                                    |

| cancelWshMetaData (int reqId)                                                                                                                                      | void                                                                                                                                                                                                                                                                                                           | Cancels pending request for WSH metadata. More…                                                                                                                                                                                                                                                                                                                                                                                                                   |

| reqWshEventData (int reqId                                                                                                                                         | void                                                                                                                                                                                                                                                                                                           | WshEventData wshEventData)                                                                                                                                                                                                                                                                                                                                                                                                                                        |

| cancelWshEventData (int reqId)                                                                                                                                     | void                                                                                                                                                                                                                                                                                                           | Cancels pending WSH event data request. More…                                                                                                                                                                                                                                                                                                                                                                                                                     |

| reqUserInfo (int reqId)                                                                                                                                            | void                                                                                                                                                                                                                                                                                                           | Requests user info. More…                                                                                                                                                                                                                                                                                                                                                                                                                                         |

| IsDataAvailable ()                                                                                                                                                 | bool                                                                                                                                                                                                                                                                                                           | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| ReadInt ()                                                                                                                                                         | int                                                                                                                                                                                                                                                                                                            | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| ReadAtLeastNBytes (int msgSize)                                                                                                                                    | byte\\\[\]                                                                                                                                                                                                                                                                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

| ReadByteArray (int msgSize)                                                                                                                                        | byte\\\[\]                                                                                                                                                                                                                                                                                                        | None                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

&nbsp;

\---

&nbsp;

\#\# title: Public Attributes

&nbsp;

| Name                           | Type | Description                                                                                                                                                                      |

| \------------------------------ | \---- | \-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| ServerVersion \=\> serverVersion | int  | returns the Host's version. Some of the API functionality might not be available in older Hosts and therefore it is essential to keep the TWS/Gateway as up to date as possible. |

&nbsp;

\---

&nbsp;

\#\# title: Public Attributes

&nbsp;

| Name                           | Type | Description                                                                                                                                                                      |

| \------------------------------ | \---- | \-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| ServerVersion \=\> serverVersion | int  | returns the Host's version. Some of the API functionality might not be available in older Hosts and therefore it is essential to keep the TWS/Gateway as up to date as possible. |

&nbsp;

\---

&nbsp;

\#\# title: Protected Attributes

&nbsp;

| Name               | Type          | Description |

| \------------------ | \------------- | \----------- |

| serverVersion      | int           | None        |

| socketTransport    | ETransport    | None        |

| wrapper            | EWrapper      | None        |

| isConnected        | volatile bool | None        |

| clientId           | int           | None        |

| extraAuth          | bool          | None        |

| useV100Plus \= true | bool          | None        |

| allowRedirect      | bool          | None        |

| tcpStream          | Stream        | None        |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

TWS/Gateway client class This client class contains all the available methods to communicate with IB. Up to 32 clients can be connected to a single instance of the TWS/Gateway simultaneously. From herein, the TWS/Gateway will be referred to as the Host.

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                               | Type                 | Description                                             |

| \---------------------------------- | \-------------------- | \------------------------------------------------------- |

| serverVersion (int version         | void EClientMsgSink. | string time)                                            |

| eConnect (string host              | void                 | int port                                                |

| eConnect (string host              | void                 | int port                                                |

| redirect (string host)             | void                 | Redirects connection to different host.                 |

| eDisconnect (bool resetState=true) | override void        | Closes the socket connection and terminates its thread. |

&nbsp;

\---

&nbsp;

\#\# title: Protected Member Functions

&nbsp;

| Name                                    | Type           | Description     |

| \--------------------------------------- | \-------------- | \--------------- |

| createClientStream (string host         | virtual Stream | int port)       |

| prepareBuffer (BinaryWriter paramsList) | override uint  | None            |

| CloseAndSend (BinaryWriter request      | override void  | uint lengthPos) |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Captures incoming messages to the API client and places them into a queue.

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                 | Type | Description |

| \-------------------- | \---- | \----------- |

| Start ()             | void | None        |

| processMsgs ()       | void | None        |

| putMessageToQueue () | bool | None        |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Notifies the thread reading information from the TWS whenever there are messages ready to be consumed. Not currently used in Python API.

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name             | Type | Description                                                                   |

| \---------------- | \---- | \----------------------------------------------------------------------------- |

| issueSignal ()   | void | Issues a signal to the consuming thread when there are things to be consumed. |

| waitForSignal () | void | Makes the consuming thread waiting until a signal is issued.                  |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name             | Type | Description                                                                   |

| \---------------- | \---- | \----------------------------------------------------------------------------- |

| issueSignal ()   | void | Issues a signal to the consuming thread when there are things to be consumed. |

| waitForSignal () | void | Makes the consuming thread waiting until a signal is issued.                  |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                                                                                                                                                         | Type                                                            | Description                                                                                                                                                                                                                                                     |

| \------------------------------------------------------------------------------------------------------------------------------------------------------------ | \--------------------------------------------------------------- | \--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| error (Exception e)                                                                                                                                          | void                                                            | Handles errors generated within the API itself. If an exception is thrown within the API code it will be notified here. Possible cases include errors while reading the information from the socket or even mishandling at EWrapper's implementing class. More… |

| error (string str)                                                                                                                                           | void                                                            | None                                                                                                                                                                                                                                                            |

| error (int id                                                                                                                                                | void                                                            | int errorCode                                                                                                                                                                                                                                                   |

| currentTime (long time)                                                                                                                                      | void                                                            | TWS's current time. TWS is synchronized with the server (not local computer) using NTP and this function will receive the current time in TWS. More…                                                                                                            |

| tickPrice (int tickerId                                                                                                                                      | void                                                            | int field                                                                                                                                                                                                                                                       |

| tickSize (int tickerId                                                                                                                                       | void                                                            | int field                                                                                                                                                                                                                                                       |

| tickString (int tickerId                                                                                                                                     | void                                                            | int field                                                                                                                                                                                                                                                       |

| tickGeneric (int tickerId                                                                                                                                    | void                                                            | int field                                                                                                                                                                                                                                                       |

| tickEFP (int tickerId                                                                                                                                        | void                                                            | int tickType                                                                                                                                                                                                                                                    |

| deltaNeutralValidation (int reqId                                                                                                                            | void                                                            | DeltaNeutralContract deltaNeutralContract)                                                                                                                                                                                                                      |

| the server sends a deltaNeutralValidation() message with the DeltaNeutralContract structure. If the delta and price fields are empty in the original request | Upon accepting a Delta-Neutral DN RFQ(request for quote)        | the confirmation will contain the current values from the server. These values are locked when RFQ is processed and remain locked until the RFQ is cancelled.                                                                                                   |

| None                                                                                                                                                         | More…                                                           | None                                                                                                                                                                                                                                                            |

| tickOptionComputation (int tickerId                                                                                                                          | void                                                            | int field                                                                                                                                                                                                                                                       |

| tickSnapshotEnd (int tickerId)                                                                                                                               | void                                                            | When requesting market data snapshots                                                                                                                                                                                                                           |

| nextValidId (int orderId)                                                                                                                                    | void                                                            | Receives next valid order id. Will be invoked automatically upon successfull API client connection                                                                                                                                                              |

| managedAccounts (string accountsList)                                                                                                                        | void                                                            | Receives a comma-separated string with the managed account ids. Occurs automatically on initial API client connection. More…                                                                                                                                    |

| connectionClosed ()                                                                                                                                          | void                                                            | Callback to indicate the API connection has closed. Following a API TWS broken socket connection                                                                                                                                                                |

| accountSummary (int reqId                                                                                                                                    | void                                                            | string account                                                                                                                                                                                                                                                  |

| accountSummaryEnd (int reqId)                                                                                                                                | void                                                            | notifies when all the accounts' information has ben received. Requires TWS 967+ to receive accountSummaryEnd in linked account structures. More…                                                                                                                |

| bondContractDetails (int reqId                                                                                                                               | void                                                            | ContractDetails contract)                                                                                                                                                                                                                                       |

| updateAccountValue (string key                                                                                                                               | void                                                            | string value                                                                                                                                                                                                                                                    |

| updatePortfolio (Contract contract                                                                                                                           | void                                                            | decimal position                                                                                                                                                                                                                                                |

| updateAccountTime (string timestamp)                                                                                                                         | void                                                            | Receives the last time on which the account was updated. More…                                                                                                                                                                                                  |

| accountDownloadEnd (string account)                                                                                                                          | void                                                            | Notifies when all the account's information has finished. More…                                                                                                                                                                                                 |

| orderStatus (int orderId                                                                                                                                     | void                                                            | string status                                                                                                                                                                                                                                                   |

| openOrder (int orderId                                                                                                                                       | void                                                            | Contract contract                                                                                                                                                                                                                                               |

| openOrderEnd ()                                                                                                                                              | void                                                            | Notifies the end of the open orders' reception. More…                                                                                                                                                                                                           |

| contractDetails (int reqId                                                                                                                                   | void                                                            | ContractDetails contractDetails)                                                                                                                                                                                                                                |

| contractDetailsEnd (int reqId)                                                                                                                               | void                                                            | After all contracts matching the request were returned                                                                                                                                                                                                          |

| execDetails (int reqId                                                                                                                                       | void                                                            | Contract contract                                                                                                                                                                                                                                               |

| execDetailsEnd (int reqId)                                                                                                                                   | void                                                            | indicates the end of the Execution reception. More…                                                                                                                                                                                                             |

| commissionReport (CommissionReport commissionReport)                                                                                                         | void                                                            | provides the CommissionReport of an Execution More…                                                                                                                                                                                                             |

| fundamentalData (int reqId                                                                                                                                   | void                                                            | string data)                                                                                                                                                                                                                                                    |

| historicalData (int reqId                                                                                                                                    | void                                                            | Bar bar)                                                                                                                                                                                                                                                        |

| historicalDataUpdate (int reqId                                                                                                                              | void                                                            | Bar bar)                                                                                                                                                                                                                                                        |

| historicalDataEnd (int reqId                                                                                                                                 | void                                                            | string start                                                                                                                                                                                                                                                    |

| marketDataType (int reqId                                                                                                                                    | void                                                            | int marketDataType)                                                                                                                                                                                                                                             |

| updateMktDepth (int tickerId                                                                                                                                 | void                                                            | int position                                                                                                                                                                                                                                                    |

| updateMktDepthL2 (int tickerId                                                                                                                               | void                                                            | int position                                                                                                                                                                                                                                                    |

| updateNewsBulletin (int msgId                                                                                                                                | void                                                            | int msgType                                                                                                                                                                                                                                                     |

| position (string account                                                                                                                                     | void                                                            | Contract contract                                                                                                                                                                                                                                               |

| positionEnd ()                                                                                                                                               | void                                                            | Indicates all the positions have been transmitted. More…                                                                                                                                                                                                        |

| realtimeBar (int reqId                                                                                                                                       | void                                                            | long date                                                                                                                                                                                                                                                       |

| scannerParameters (string xml)                                                                                                                               | void                                                            | provides the xml-formatted parameters available from TWS market scanners (not all available in API). More…                                                                                                                                                      |

| scannerData (int reqId                                                                                                                                       | void                                                            | int rank                                                                                                                                                                                                                                                        |

| scannerDataEnd (int reqId)                                                                                                                                   | void                                                            | Indicates the scanner data reception has terminated. More…                                                                                                                                                                                                      |

| receiveFA (int faDataType                                                                                                                                    | void                                                            | string faXmlData)                                                                                                                                                                                                                                               |

| verifyMessageAPI (string apiData)                                                                                                                            | void                                                            | Not generally available.                                                                                                                                                                                                                                        |

| verifyCompleted (bool isSuccessful                                                                                                                           | void                                                            | string errorText)                                                                                                                                                                                                                                               |

| verifyAndAuthMessageAPI (string apiData                                                                                                                      | void                                                            | string xyzChallenge)                                                                                                                                                                                                                                            |

| verifyAndAuthCompleted (bool isSuccessful                                                                                                                    | void                                                            | string errorText)                                                                                                                                                                                                                                               |

| displayGroupList (int reqId                                                                                                                                  | void                                                            | string groups)                                                                                                                                                                                                                                                  |

| displayGroupUpdated (int reqId                                                                                                                               | void                                                            | string contractInfo)                                                                                                                                                                                                                                            |

| connectAck ()                                                                                                                                                | void                                                            | callback initially acknowledging connection attempt connection handshake not complete until nextValidID is received                                                                                                                                             |

| positionMulti (int requestId                                                                                                                                 | void                                                            | string account                                                                                                                                                                                                                                                  |

| positionMultiEnd (int requestId)                                                                                                                             | void                                                            | Indicates all the positions have been transmitted. More…                                                                                                                                                                                                        |

| accountUpdateMulti (int requestId                                                                                                                            | void                                                            | string account                                                                                                                                                                                                                                                  |

| accountUpdateMultiEnd (int requestId)                                                                                                                        | void                                                            | Indicates all the account updates have been transmitted. More…                                                                                                                                                                                                  |

| securityDefinitionOptionParameter (int reqId                                                                                                                 | void                                                            | string exchange                                                                                                                                                                                                                                                 |

| securityDefinitionOptionParameterEnd (int reqId)                                                                                                             | void                                                            | called when all callbacks to securityDefinitionOptionParameter are complete More…                                                                                                                                                                               |

| softDollarTiers (int reqId                                                                                                                                   | void                                                            | SoftDollarTier\\\[\] tiers)                                                                                                                                                                                                                                        |

| familyCodes (FamilyCode\\\[\] familyCodes)                                                                                                                      | void                                                            | returns array of family codes More…                                                                                                                                                                                                                             |

| symbolSamples (int reqId                                                                                                                                     | void                                                            | ContractDescription\\\[\] contractDescriptions)                                                                                                                                                                                                                    |

| mktDepthExchanges (DepthMktDataDescription\\\[\] depthMktDataDescriptions)                                                                                      | void                                                            | called when receives Depth Market Data Descriptions More…                                                                                                                                                                                                       |

| tickNews (int tickerId                                                                                                                                       | void                                                            | long timeStamp                                                                                                                                                                                                                                                  |

| smartComponents (int reqId                                                                                                                                   | void                                                            | Dictionary\\\< int                                                                                                                                                                                                                                                |

| tickReqParams (int tickerId                                                                                                                                  | void                                                            | double minTick                                                                                                                                                                                                                                                  |

| newsProviders (NewsProvider\\\[\] newsProviders)                                                                                                                | void                                                            | returns array of subscribed API news providers for this user More…                                                                                                                                                                                              |

| newsArticle (int requestId                                                                                                                                   | void                                                            | int articleType                                                                                                                                                                                                                                                 |

| historicalNews (int requestId                                                                                                                                | void                                                            | string time                                                                                                                                                                                                                                                     |

| historicalNewsEnd (int requestId                                                                                                                             | void                                                            | bool hasMore)                                                                                                                                                                                                                                                   |

| headTimestamp (int reqId                                                                                                                                     | void                                                            | string headTimestamp)                                                                                                                                                                                                                                           |

| None                                                                                                                                                         | returns beginning of data for contract for specified data type  | None                                                                                                                                                                                                                                                            |

| None                                                                                                                                                         | More…                                                           | None                                                                                                                                                                                                                                                            |

| histogramData (int reqId                                                                                                                                     | void                                                            | HistogramEntry\\\[\] data)                                                                                                                                                                                                                                         |

| rerouteMktDataReq (int reqId                                                                                                                                 | void                                                            | int conId                                                                                                                                                                                                                                                       |

| None                                                                                                                                                         | returns conId and exchange for CFD market data request re-route | None                                                                                                                                                                                                                                                            |

| None                                                                                                                                                         | More…                                                           | None                                                                                                                                                                                                                                                            |

| rerouteMktDepthReq (int reqId                                                                                                                                | void                                                            | int conId                                                                                                                                                                                                                                                       |

| marketRule (int marketRuleId                                                                                                                                 | void                                                            | PriceIncrement\\\[\] priceIncrements)                                                                                                                                                                                                                              |

| pnl (int reqId                                                                                                                                               | void                                                            | double dailyPnL                                                                                                                                                                                                                                                 |

| pnlSingle (int reqId                                                                                                                                         | void                                                            | decimal pos                                                                                                                                                                                                                                                     |

| historicalTicks (int reqId                                                                                                                                   | void                                                            | HistoricalTick\\\[\] ticks                                                                                                                                                                                                                                         |

| historicalTicksBidAsk (int reqId                                                                                                                             | void                                                            | HistoricalTickBidAsk\\\[\] ticks                                                                                                                                                                                                                                   |

| historicalTicksLast (int reqId                                                                                                                               | void                                                            | HistoricalTickLast\\\[\] ticks                                                                                                                                                                                                                                     |

| tickByTickAllLast (int reqId                                                                                                                                 | void                                                            | int tickType                                                                                                                                                                                                                                                    |

| tickByTickBidAsk (int reqId                                                                                                                                  | void                                                            | long time                                                                                                                                                                                                                                                       |

| tickByTickMidPoint (int reqId                                                                                                                                | void                                                            | long time                                                                                                                                                                                                                                                       |

| orderBound (long orderId                                                                                                                                     | void                                                            | int apiClientId                                                                                                                                                                                                                                                 |

| completedOrder (Contract contract                                                                                                                            | void                                                            | Order order                                                                                                                                                                                                                                                     |

| completedOrdersEnd ()                                                                                                                                        | void                                                            | Notifies the end of the completed orders' reception. More…                                                                                                                                                                                                      |

| replaceFAEnd (int reqId                                                                                                                                      | void                                                            | string text)                                                                                                                                                                                                                                                    |

| wshMetaData (int reqId                                                                                                                                       | void                                                            | string dataJson)                                                                                                                                                                                                                                                |

| wshEventData (int reqId                                                                                                                                      | void                                                            | string dataJson)                                                                                                                                                                                                                                                |

| historicalSchedule (int reqId                                                                                                                                | void                                                            | string startDateTime                                                                                                                                                                                                                                            |

| userInfo (int reqId                                                                                                                                          | void                                                            | string whiteBrandingId)                                                                                                                                                                                                                                         |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Class describing an order's execution.

&nbsp;

| Name                 | Type      | Description                                                                                                                                                                                                  |

| \-------------------- | \--------- | \------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |

| OrderId              | int       | The API client's order Id. May not be unique to an account.                                                                                                                                                  |

| ClientId             | int       | The API client identifier which placed the order which originated this execution.                                                                                                                            |

| ExecId               | string    | The execution's identifier. Each partial fill has a separate ExecId. A correction is indicated by an ExecId which differs from a previous ExecId in only the digits after the final period                   |

| Time                 | string    | The execution's server time.                                                                                                                                                                                 |

| AcctNumber           | string    | The account to which the order was allocated.                                                                                                                                                                |

| Exchange             | string    | The exchange where the execution took place.                                                                                                                                                                 |

| Side                 | string    | Specifies if the transaction was buy or sale BOT for bought                                                                                                                                                  |

| Shares               | decimal   | The number of shares filled.                                                                                                                                                                                 |

| Price                | double    | The order's execution price excluding commissions.                                                                                                                                                           |

| PermId               | int       | The TWS order identifier. The PermId can be 0 for trades originating outside IB.                                                                                                                             |

| Liquidation          | int       | Identifies whether an execution occurred because of an IB-initiated liquidation.                                                                                                                             |

| CumQty               | decimal   | Cumulative quantity. Used in regular trades                                                                                                                                                                  |

| AvgPrice             | double    | Average price. Used in regular trades                                                                                                                                                                        |

| OrderRef             | string    | The OrderRef is a user-customizable string that can be set from the API or TWS and will be associated with an order for its lifetime.                                                                        |

| EvRule               | string    | The Economic Value Rule name and the respective optional argument. The two values should be separated by a colon. For example                                                                                |

| EvMultiplier         | double    | Tells you approximately how much the market value of a contract would change if the price were to change by 1\. It cannot be used to get market value by multiplying the price by the approximate multiplier. |

| ModelCode            | string    | model code                                                                                                                                                                                                   |

| LastLiquidity        | Liquidity | The liquidity type of the execution. Requires TWS 968+ and API v973.05+. Python API specifically requires API v973.06+.                                                                                      |

| PendingPriceRevision | bool      | pending price revision                                                                                                                                                                                       |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                | Type          | Description |

| \------------------- | \------------- | \----------- |

| Equals (object obj) | override bool |             |

| GetHashCode ()      | override int  |             |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

This class represents a condition requiring a specific execution event to be fulfilled. Orders can be activated or canceled if a set of given conditions is met. An ExecutionCondition is met whenever a trade occurs on a certain product at the given exchange.

&nbsp;

| Name     | Type   | Description                                   |

| \-------- | \------ | \--------------------------------------------- |

| Exchange | string | Exchange where the symbol is being monitored. |

| SecType  | string | Asset type being monitored.                   |

| Symbol   | string | Instrument's symbol.                          |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                               | Type            | Description                |

| \---------------------------------- | \--------------- | \-------------------------- |

| ToString()                         | override string | Returns string to display. |

| Equals (object obj)                | override bool   |                            |

| GetHashCode ()                     | override int    |                            |

| Deserialize (IDecoder inStream)    | override void   |                            |

| Serialize (BinaryWriter outStream) | override void   |                            |

&nbsp;

\---

&nbsp;

\#\# title: Protected Member Functions

&nbsp;

| Name                  | Type          | Description                                    |

| \--------------------- | \------------- | \---------------------------------------------- |

| TryParse(string cond) | override bool | Validates the price condition format is valid. |

&nbsp;

**\---**

&nbsp;

**\#\# title: Introduction**

&nbsp;

**When requesting executions, a filter can be specified to receive only a subset of them.**

&nbsp;

**| Name          | Type              | Description                                                                                                                                                                                                                                                                              |**

**| \------------- | \----------------- | \---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |**

**| AcctCode      | String            | Account identifier that executed the trade.                                                                                                                                                                                                                                              |**

**| ClientId      | Integer           | Client identifier the order was submitted through.                                                                                                                                                                                                                                       |**

**| Exchange      | string            | Exchange where the symbol was traded.                                                                                                                                                                                                                                                    |**

**| LastNDays     | Integer           | Number of previous days to receive trades for. Maximum 7\.                                                                                                                                                                                                                                |**

**| SecType       | string            | Asset type being monitored.                                                                                                                                                                                                                                                              |**

**| Side          | String            | Determine if only Buy or Sell orders are returned.                                                                                                                                                                                                                                       |**

**| SpecificDates | Array of Integers | Retrieve a specific date within the past week to receive executions for. May be used with Time, but only the executions on the Specified Dates will return.  Array formatted as \\\[YYYYMMDD\]                                                                                              |**

**| Symbol        | string            | Instrument's symbol.                                                                                                                                                                                                                                                                     |**

**| Time          | String            | Declare the date/time to receive executions at and after the designated time. Can be used in combination with LastNDays or SpecificDates.  Requests should be formatted as "YYYYMMDD HH:mm:ss TMZ" or in UTC as "YYYYMMDD-HH:mm:ss".  If no date is passed, the current date is assumed. |**

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                | Type          | Description |

| \------------------- | \------------- | \----------- |

| Equals (object obj) | override bool |             |

| GetHashCode ()      | override int  |             |

&nbsp;

\---

&nbsp;

\#\# title: HistoricalTick Class Reference

&nbsp;

Used when requesting historical tick data with whatToShow \= MIDPOINT.

&nbsp;

| Name  | Type    | Description |

| \----- | \------- | \----------- |

| Time  | long    |             |

| Price | double  |             |

| Size  | decimal |             |

&nbsp;

\---

&nbsp;

\#\# title: HistoricalTickBidAsk Class Reference

&nbsp;

Used when requesting historical tick data with whatToShow \= BID\\\_ASK.

&nbsp;

| Name              | Type           | Description                                                                                                                                      |

| \----------------- | \-------------- | \------------------------------------------------------------------------------------------------------------------------------------------------ |

| Time              | long           | The UNIX timestamp of the historical tick.                                                                                                       |

| TickAttribLast    | TickAttribLast | Tick attribs of historical last tick.                                                                                                            |

| Price             | double         | The last price of the historical tick.                                                                                                           |

| Size              | decimal        | The last size of the historical tick.                                                                                                            |

| Exchange          | string         | The source exchange of the historical tick.                                                                                                      |

| SpecialConditions | string         | The conditions of the historical tick. Refer to \[Trade Conditions\](https://www.interactivebrokers.com/en/index.php?f=7235) page for more details |

&nbsp;

\---

&nbsp;

\#\# title: HistoricalTickLast Class Reference

&nbsp;

Used when requesting historical tick data with whatToShow \= TRADES.

&nbsp;

| Name              | Type           | Description                                                                                                                                       |

| \----------------- | \-------------- | \------------------------------------------------------------------------------------------------------------------------------------------------- |

| Time              | long           | The UNIX timestamp of the historical tick.                                                                                                        |

| TickAttribLast    | TickAttribLast | Tick attribs of historical last tick.                                                                                                             |

| Price             | double         | The last price of the historical tick.                                                                                                            |

| Size              | decimal        | The last size of the historical tick.                                                                                                             |

| Exchange          | string         | The source exchange of the historical tick.                                                                                                       |

| SpecialConditions | string         | The conditions of the historical tick. Refer to \[Trade Conditions\](https://www.interactivebrokers.com/en/index.php?f=7235) page for more details. |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Class describing the liquidity type of an execution.

&nbsp;

| Name  | Type | Description                      |

| \----- | \---- | \-------------------------------- |

| Value | int  | The value of the liquidity type. |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name       | Type            | Description                |

| \---------- | \--------------- | \-------------------------- |

| ToString() | override string | Returns string to display. |

&nbsp;

\---

&nbsp;

\#\# title: MarginCondition Class Reference

&nbsp;

Used with conditional orders to cancel or submit order based on price of an instrument.

&nbsp;

| Name    | Type                                                                                                  | Description                              |

| \------- | \----------------------------------------------------------------------------------------------------- | \---------------------------------------- |

| Percent | override integer                                                                                      | The margin cushion percentage available. |

| IsMore  | Booleantd\> Determine if the MarginCondition should trigger while more or less than the percent value. |                                          |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

| Name                           | Type           | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |   |

| \------------------------------ | \-------------- | \---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | \- |

| Account                        | string         | The account the trade will be allocated to.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |   |

| Action                         | string         | Identifies the side. Generally available values are BUY and SELL. Additionally, \\\<b\>SSHORT\\\</b\> and \\\<b\>SLONG\\\</b\> are available in some institutional-accounts only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |   |

| ActiveStartTime \= new List()   | string         | Defines the start time of GTC orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |   |

| ActiveStopTime                 | string         | Defines the stop time of GTC orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |   |

| AdjustableTrailingUnit         | int            | Adjusted Stop orders: specifies where the trailing unit is an amount (set to 0\) or a percentage (set to 1\)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |   |

| AdjustedOrderType              | string         | Adjusted Stop orders: the parent order will be adjusted to the given type when the adjusted trigger price is penetrated.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |   |

| AdjustedStopLimitPrice         | double         | Adjusted Stop orders: specifies the stop limit price of the adjusted (STPL LMT) parent.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |   |

| AdjustedStopPrice              | double         | Adjusted Stop orders: specifies the stop price of the adjusted (STP) parent.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |   |

| AdjustedTrailingAmount         | double         | Adjusted Stop orders: specifies the trailing amount of the adjusted (TRAIL) parent.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |   |

| AdvancedErrorOverride          | string         | Accepts a string with parameters obtained from advancedOrderRejectJson.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |   |

| AlgoId                         | string         | Identifies orders generated by algorithmic trading.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |   |

| AlgoParams                     | List           | The list of parameters for the IB algorithm. For more information about IB's API algorithms                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |   |

| AlgoStrategy                   | string         | The algorithm strategy. ArrivalPx – Arrival Price DarkIce – Dark Ice PctVol – Percentage of Volume Twap – TWAP (Time Weighted Average Price) Vwap – VWAP (Volume Weighted Average Price) For more information about IB's API algorithms                                                                                                                                                                                                                                                                                                                                                                                                        |   |

| AllOrNone                      | bool           | Indicates whether or not all the order has to be filled on a single execution.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |   |

| AuctionStrategy                | int            | For BOX orders only. Values include: 1 – Match 2 – Improvement 3 – Transparent.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |   |

| AutoCancelDate                 | string         | Specifies the date to auto cancel the order.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |   |

| AutoCancelParent               | bool           | Cancels the parent order if child order was cancelled.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |   |

| AuxPrice                       | double         | Generic field to contain the stop price for STP LMT orders, trailing amount, etc.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| BasisPoints                    | double         | Specifies Basis Points for EFP order. The values increment in 0.01% \= 1 basis point. For EFP orders only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |   |

| BasisPointsType                | int            | Specifies the increment of the Basis Points. For EFP orders only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| BlockOrder                     | bool           | If set to true                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |   |

| CashQty                        | double         | The native cash quantity.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |   |

| ClearingAccount                | string         | Specifies the true beneficiary of the order. For IBExecution customers. This value is required for FUT/FOP orders for reporting to the exchange.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |   |

| ClearingIntent                 | string         | For execution-only clients to know where do they want their shares to be cleared at. Valid values are: IB                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |   |

| ClientId                       | int            | The API client id which placed the order.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |   |

| CompeteAgainstBestOffset       | double         | Dpecifies the offset Off The Midpoint that will be applied to the order. For IBKRATS orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |   |

| Conditions                     | List           | Conditions determining when the order will be activated or canceled.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |   |

| ConditionsCancelOrder          | bool           | Conditions can determine if an order should become active or canceled.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |   |

| ConditionsIgnoreRth            | bool           | Indicates whether or not conditions will also be valid outside Regular Trading Hours.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |   |

| ContinuousUpdate               | int            | Specifies whether TWS will automatically update the limit price of the order as the underlying price moves. VOL orders only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |   |

| Deactivate                     | Boolean        | Determines if the order is Active (False) or Deactivated (True). Orders that are deactivated are not submitted and will not execute, though they can be reviewed and transmitted via API, Trader Workstation, or Client Portal.  This is unique from the Transmit field as orders submitted as Transmit=False will not leave the current TWS instance, and will be erased upon logout. Deactivated orders will persist internally at Interactive Brokers.                                                                                                                                                                                      |   |

| Delta                          | double         | The stock's Delta. For orders on BOX only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |   |

| DeltaNeutralAuxPrice           | double         | Use this field to enter a value if the value in the deltaNeutralOrderType field is an order type that requires an Aux price                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |   |

| DeltaNeutralClearingAccount    | string         | Specifies the beneficiary of the Delta Neutral order.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |   |

| DeltaNeutralClearingIntent     | string         | Specifies where the clients want their shares to be cleared at. Must be specified by execution-only clients. Valid values are: IB                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| DeltaNeutralConId              | int            | The unique contract identifier specifying the security in Delta Neutral order.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |   |

| DeltaNeutralDesignatedLocation | string         | Identifies third party order origin. Used only when deltaNeutralShortSaleSlot \= 2\.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |   |

| DeltaNeutralOpenClose          | string         | Specifies whether the order is an Open or a Close order and is used when the hedge involves a CFD and and the order is clearing away.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |   |

| DeltaNeutralOrderType          | string         | Enter an order type to instruct TWS to submit a delta neutral trade on full or partial execution of the VOL order. VOL orders only. For no hedge delta order to be sent                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |   |

| DeltaNeutralSettlingFirm       | string         | Indicates the firm which will settle the Delta Neutral trade. Institutions only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |   |

| DeltaNeutralShortSale          | bool           | Used when the hedge involves a stock and indicates whether or not it is sold short.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |   |

| DeltaNeutralShortSaleSlot      | int            | Indicates a short sale Delta Neutral order. Has a value of 1 (the clearing broker holds shares) or 2 (delivered from a third party). If you use 2                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| DesignatedLocation             | string         | For institutions only. Indicates the location where the shares to short come from. Used only when short sale slot is set to 2 (which means that the shares to short are held elsewhere and not with IB).                                                                                                                                                                                                                                                                                                                                                                                                                                       |   |

| DiscretionaryAmt               | double         | The amount off the limit price allowed for discretionary orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |   |

| DiscretionaryUpToLimitPrice    | bool           | Set to true to convert order of type 'Primary Peg' to 'D-Peg'.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |   |

| DisplaySize                    | int            | The publicly disclosed order size                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| DontUseAutoPriceForHedge       | bool           | Don't use auto price for hedge.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |   |

| Duration                       | int            | Specifies the number of seconds the order should remain active. For GTD orders only.  Users that would prefer to specify an exact date should user the "GoodTillDate" parameter instead.  Both values cannot be specified at the same time.                                                                                                                                                                                                                                                                                                                                                                                                    |   |

| ExemptCode                     | int            | Only available with IB Execution-Only accounts with applicable securities. Mark order as exempt from short sale uptick rule.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |   |

| ExtOperator                    | String         | Following CME Rule 576, the ExtOperator field will signify if the unique API operator at the time of trading for order management.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |   |

| FaGroup                        | string         | The Financial Advisor group the trade will be allocated to. Use an empty string if not applicable.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |   |

| FaMethod                       | string         | The Financial Advisor allocation method the trade will be allocated to. Use an empty string if not applicable.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |   |

| FaPercentage                   | string         | The Financial Advisor percentage concerning the trade's allocation. Use an empty string if not applicable.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |   |

| FilledQuantity                 | decimal        | Specifies the initial order quantity to be filled.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |   |

| GoodAfterTime                  | string         | Specifies the date and time after which the order will be active. Format: yyyymmdd hh:mm:ss \\{optional Timezone}.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| GoodTillDate                   | string         | The date and time when the order should cancel if not already filled. Only valid for orders using the "GTD" tif.  Users that would prefer to specify a number of seconds should use the Duration parameter instead.  Both values cannot be specified at the same time.                                                                                                                                                                                                                                                                                                                                                                         |   |

| HedgeMaxSize                   | integer        | hedgeMaxSize (also referred to as "Max Hedging Size") is a user-supplied parameter that caps the maximum number of shares that can be shorted in a beta  hedge child order. It provides an upper bound for risk and credit assessment purposes. Applied only to beta hedge orders (sell side only) for stocks in IB-  cleared accounts.                                                                                                                                                                                                                                                                                                        |   |

| HedgeParam                     | string         | For hedge orders. Beta \= x for Beta hedge orders                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |   |

| HedgeType                      | string         | For hedge orders. Possible values include: D – Delta B – Beta F – FX P – Pair                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |   |

| Hidden                         | bool           | If set to true, the order will not be visible when viewing the market depth. This option only applies to orders routed to the NASDAQ exchange.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |   |

| ImbalanceOnly                  | bool           | Used to specify "imbalance only open orders" or "imbalance only closing orders".                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |   |

| includeOvernight               | bool           | Specify if the order should include overnight trading or not. False (no Overnight) is set by default.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |   |

| IsOmsContainer                 | bool           | Set to true to create tickets from API orders when TWS is used as an OMS.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |   |

| IsPeggedChangeAmountDecrease   | bool           | Pegged-to-benchmark orders: indicates whether the order's pegged price should increase or decreases.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |   |

| LmtPrice                       | double         | The LIMIT price. Used for limit                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |   |

| LmtPriceOffset                 | double         | Adjusted Stop orders: specifies the price offset for the stop to move in increments.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |   |

| ManualOrderIndicator           | int            | Following CME Rule 576, the ManualOrderIndicator field will signify if an order is manual (1) or automated (0).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |   |

| ManualOrderTime                | string         | Used by brokers and advisors when manually entering an order request. Format should be "YYYYMMDD-HH:mm:ss" using UTC as the timezone value.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |   |

| MidOffsetAtHalf                | double         | This offset is applied when the spread is an odd number of cents wide. This offset must be in half-penny increments. For IBKRATS orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |   |

| MidOffsetAtWhole               | double         | This offset is applied when the spread is an even number of cents wide. This offset must be in whole-penny increments or zero. For IBKRATS orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |   |

| Mifid2DecisionAlgo             | string         | Identifies the algorithm responsible for investment decisions within the firm. Orders covered under MiFID 2 must include either Mifid2DecisionMaker or Mifid2DecisionAlgo                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |   |

| Mifid2DecisionMaker            | string         | Identifies a person as the responsible party for investment decisions within the firm. Orders covered by MiFID 2 (Markets in Financial Instruments Directive 2\) must include either Mifid2DecisionMaker or Mifid2DecisionAlgo field (but not both). Requires TWS 969+.                                                                                                                                                                                                                                                                                                                                                                         |   |

| Mifid2ExecutionAlgo            | string         | For MiFID 2 reporting; identifies the algorithm responsible for the execution of a transaction within the firm. Requires TWS 969+.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |   |

| Mifid2ExecutionTrader          | string         | For MiFID 2 reporting; identifies a person as the responsible party for the execution of a transaction within the firm. Requires TWS 969+.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |   |

| MinCompeteSize                 | int            | Defines the minimum size to compete. For IBKRATS orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |   |

| MinQty                         | int            | Identifies a minimum quantity order type.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |   |

| MinTradeQty                    | int            | Defines the minimum trade quantity to fill. For IBKRATS orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |   |

| ModelCode                      | string         | Is used to place an order to a model. For example                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| NotHeld                        | bool           | Orders routed to IBDARK are tagged as "post only" and are held in IB's order book                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| OcaGroup                       | string         | One-Cancels-All group identifier.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| OcaType                        | int            | Tells how to handle remaining orders in an OCA group when one order or part of an order executes. Valid values are: 1 – Cancel all remaining orders with block. 2 – Remaining orders are proportionately reduced in size with block. 3 – Remaining orders are proportionately reduced in size with no block. If you use a value "with block" it gives the order overfill protection. This means that only one order in the group will be routed at a time to remove the possibility of an overfill.                                                                                                                                            |   |

| OpenClose                      | string         | For institutional customers only. Valid values are O (open) and C (close). Available for institutional clients to determine if this order is to open or close a position. When Action \= "BUY" and OpenClose \= "O" this will open a new position. When Action \= "BUY" and OpenClose \= "C" this will close and existing short position.                                                                                                                                                                                                                                                                                                          |   |

| OptOutSmartRouting             | bool           | Use to opt out of default SmartRouting for orders routed directly to ASX. This attribute defaults to false unless explicitly set to true. When set to false                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |   |

| OrderComboLegs                 | List           | List of Per-leg price following the same sequence combo legs are added. The combo price must be left unspecified when using per-leg prices.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |   |

| OrderId                        | int            | The API client's order id.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |   |

| OrderMiscOptions \= new List()  | List           | For internal use only. Use the default value XYZ.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| OrderRef                       | string         | The order reference. Intended for institutional customers only                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |   |

| OrderType                      | string         | The order's type.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| Origin                         | int            | The order's origin. Same as TWS "Origin" column. Identifies the type of customer from which the order originated. Valid values are:0 – Customer 1 – Firm.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |   |

| OutsideRth                     | bool           | If set to true, allows orders to also trigger or fill outside of regular trading hours.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |   |

| OverridePercentageConstraints  | bool           | Overrides TWS constraints. Precautionary constraints are defined on the TWS Presets page                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |   |

| ParentId                       | int            | The order ID of the parent order, used for bracket and auto trailing stop orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| ParentPermId                   | long           | Parent order Id.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |   |

| PeggedChangeAmount             | double         | Pegged-to-benchmark orders: amount by which the order's pegged price should move.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| PercentOffset                  | double         | The percent offset amount for relative orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |   |

| PermId                         | int            | The Host order identifier.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |   |

| PostToAts                      | int            | Value must be positive                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |   |

| PtOrderId                      | int            | Order ID for a preset profit taker order.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |   |

| PtOrderType                    | string         | Order type for the profit take. Must be "PRESET".                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| RandomizePrice                 | bool           | Randomizes the order's price. Only for Volatility and Pegged to Volatility orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |   |

| RandomizeSize                  | bool           | Randomizes the order's size. Only for Volatility and Pegged to Volatility orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| RefFuturesConId                | int            | Identifies the reference future conId.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |   |

| ReferenceChangeAmount          | double         | Pegged-to-benchmark orders: the amount the reference contract needs to move to adjust the pegged order.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |   |

| ReferenceContractId            | int            | Pegged-to-benchmark orders: this attribute will contain the conId of the contract against which the order will be pegged.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |   |

| ReferenceExchange              | string         | Pegged-to-benchmark orders: the exchange against which we want to observe the reference contract.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| ReferencePriceType             | int            | Specifies how you want TWS to calculate the limit price for options                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |   |

| RouteMarketableToBbo           | bool           | Routes market order to Best Bid Offer.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |   |

| Rule80A                        | string         | Individual \= 'I' Agency \= 'A' AgentOtherMember \= 'W' IndividualPTIA \= 'J' AgencyPTIA \= 'U' AgentOtherMemberPTIA \= 'M' IndividualPT \= 'K' AgencyPT \= 'Y' AgentOtherMemberPT \= 'N'.                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| ScaleAutoReset                 | bool           | Restarts the Scale series if the order is cancelled. For extended scale orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |   |

| ScaleInitFillQty               | int            | Specifies the initial quantity to be filled. For extended scale orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |   |

| ScaleInitLevelSize             | int            | Defines the size of the first                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |   |

| ScaleInitPosition              | int            | The initial position of the Scale order. For extended scale orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |   |

| ScalePriceAdjustInterval       | int            | Specifies the interval when the price is adjusted. For extended Scale orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |   |

| ScalePriceAdjustValue          | double         | Modifies the value of the Scale order. For extended Scale orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |   |

| ScalePriceIncrement            | double         | Defines the price increment between scale components. For Scale orders only. This value is compulsory.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |   |

| ScaleProfitOffset              | double         | Specifies the offset when to adjust profit. For extended scale orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |   |

| ScaleRandomPercent             | bool           | Defines the random percent by which to adjust the position. For extended scale orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |   |

| ScaleSubsLevelSize             | int            | Defines the order size of the subsequent scale order components. For Scale orders only. Used in conjunction with scaleInitLevelSize().                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |   |

| ScaleTable                     | string         | The list of scale orders. Used for scale orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |   |

| SettlingFirm                   | string         | Indicates the firm which will settle the trade. Institutions only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |   |

| Shareholder                    | string         | Identifies the Shareholder.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |   |

| ShortSaleSlot                  | int            | For institutions only. Valid values are: 1 – Broker holds shares 2 – Shares come from elsewhere.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |   |

|                                |                |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |   |

| \---                            | \---            | \---                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |   |

| SlOrderId                      | int            | Order identifier of the attached stop loss from presets.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |   |

| SlOrderType                    | string         | Order type for the attach stop loss from presets. Must be "PRESET".                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |   |

| SmartComboRoutingParams        | List           | Advanced parameters for Smart combo routing. These features are for both guaranteed and nonguaranteed combination orders routed to Smart                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |   |

| Solicited                      | bool           | The Solicited field should be used for orders initiated or recommended by the broker or adviser that were approved by the client (by phone, email, chat, verbally, etc.) prior to entry. Please note that orders that the adviser or broker placed without specifically discussing with the client are discretionary orders, not solicited.                                                                                                                                                                                                                                                                                                    |   |

| StartingPrice                  | double         | The auction's starting price. For BOX orders only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |   |

| StockRangeLower                | double         | The lower value for the acceptable underlying stock price range. For price improvement option orders on BOX and VOL orders with dynamic management.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |   |

| StockRangeUpper                | double         | The upper value for the acceptable underlying stock price range. For price improvement option orders on BOX and VOL orders with dynamic management.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |   |

| StockRefPrice                  | double         | The stock's reference price. The reference price is used for VOL orders to compute the limit price sent to an exchange (whether or not Continuous Update is selected)                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |   |

| SweepToFill                    | bool           | If set to true                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |   |

| Tier                           | SoftDollarTier | Define the Soft Dollar Tier used for the order. Only provided for registered professional advisors and hedge and mutual funds.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |   |

| Tif                            | string         | The time in force. Valid values are: DAY – Valid for the day only. GTC – Good until canceled. The order will continue to work within the system and in the marketplace until it executes or is canceled. GTC orders will be automatically be cancelled under the following conditions: If a corporate action on a security results in a stock split (forward or reverse)                                                                                                                                                                                                                                                                       |   |

| TotalQuantity                  | decimal        | The number of positions being bought/sold.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |   |

| TrailStopPrice                 | double         | Trail stop price for TRAIL LIMIT orders.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |   |

| TrailingPercent                | double         | Specifies the trailing amount of a trailing stop order as a percentage. Observe the following guidelines when using the trailingPercent field:  Guidelines  \\\* This field is mutually exclusive with the existing trailing amount. That is, the API client can send one or the other but not both. \\\* This field is read AFTER the stop price (barrier price) as follows: deltaNeutralAuxPrice stopPrice, trailingPercent, scale order attributes. \\\* The field will also be sent to the API in the openOrder message if the API client version is \>= 56\. It is sent after the stopPrice field as follows: stopPrice, trailingPct, basisPoint. |   |

| Transmit                       | bool           | Specifies whether the order will be transmitted by TWS. If set to false, the order will be created at TWS but will not be sent.  Users implementing directly from Protobuf should be aware that Transmit should be implicitly set to 'true' when placing orders to transmit an order.                                                                                                                                                                                                                                                                                                                                                          |   |

| TriggerMethod                  | int            | Specifies how Simulated Stop                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |   |

| TriggerPrice                   | double         | Adjusted Stop orders: specifies the trigger price to execute.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |   |

| UsePriceMgmtAlgo               | bool           | Specifies wether to use Price Management Algo. CTCI users only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |   |

| Volatility                     | double         | The option price in volatility                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |   |

| VolatilityType                 | int            | Values include: 1 – Daily Volatility 2 – Annual Volatility.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |   |

| WhatIf                         | bool           | Allows to retrieve the commissions and margin information. When placing an order with this attribute set to true                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |   |

| customerAccount                | String         | Required for Nondisclosed Omnibus Accounts. A unique identifier for each account within the Omnibus structure to signify the account holder being traded. Best practice (Not Required): clients should look to hash this value, using something along the lines of 5 digits of SHA1 of the account number. This should not be implemented for non-omnibus accounts.                                                                                                                                                                                                                                                                            |   |

| isProCustomer                  | Boolean        | Required for Nondisclosed Omnibus Accounts Signify whether or not the subaccount is classified as Professional or Non-Professional. This should not be implemented for non-omnibus accounts.                                                                                                                                                                                                                                                                                                                                                                                                                                                   |   |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                | Type          | Description |

| \------------------- | \------------- | \----------- |

| Equals (object obj) | override bool |             |

| GetHashCode ()      | override int  |             |

&nbsp;

\---

&nbsp;

\#\# title: Static Public Member Functions

&nbsp;

| Name                                                                  | Type          | Description |

| \--------------------------------------------------------------------- | \------------- | \----------- |

| CUSTOMER \= 0                                                          | static int    |             |

| FIRM \= 1                                                              | static int    |             |

| OPT\\\_UNKNOWN \= '?'                                                    | static char   |             |

| OPT\\\_BROKER\\\_DEALER \= 'b'                                             | static char   |             |

| OPT\\\_CUSTOMER \= 'c'                                                   | static char   |             |

| OPT\\\_FIRM \= 'f'                                                       | static char   |             |

| OPT\\\_ISEMM \= 'm'                                                      | static char   |             |

| OPT\\\_FARMM \= 'n'                                                      | static char   |             |

| OPT\\\_SPECIALIST \= 'y'                                                 | static char   |             |

| AUCTION\\\_MATCH \= 1                                                    | static int    |             |

| AUCTION\\\_IMPROVEMENT \= 2                                              | static int    |             |

| AUCTION\\\_TRANSPARENT \= 3                                              | static int    |             |

| EMPTY\\\_STR \= ""                                                       | static string |             |

| COMPETE\\\_AGAINST\\\_BEST\\\_OFFSET\\\_UP\\\_TO\\\_MID \= double.PositiveInfinity | static double | static int  |

| FIRM \= 1                                                              | static int    |             |

| OPT\\\_UNKNOWN \= '?'                                                    | static char   |             |

| OPT\\\_BROKER\\\_DEALER \= 'b'                                             | static char   |             |

| OPT\\\_CUSTOMER \= 'c'                                                   | static char   |             |

| OPT\\\_FIRM \= 'f'                                                       | static char   |             |

| OPT\\\_ISEMM \= 'm'                                                      | static char   |             |

| OPT\\\_FARMM \= 'n'                                                      | static char   |             |

| OPT\\\_SPECIALIST \= 'y'                                                 | static char   |             |

| AUCTION\\\_MATCH \= 1                                                    | static int    |             |

| AUCTION\\\_IMPROVEMENT \= 2                                              | static int    |             |

| AUCTION\\\_TRANSPARENT \= 3                                              | static int    |             |

| EMPTY\\\_STR \= ""                                                       | static string |             |

| COMPETE\\\_AGAINST\\\_BEST\\\_OFFSET\\\_UP\\\_TO\\\_MID \= double.PositiveInfinity | static double | None        |

&nbsp;

\---

&nbsp;

\#\# title: OrderAllocation Class Reference

&nbsp;

The OrderAllocation class to denote an advisor's allocations while trading subaccounts.

&nbsp;

| Name            | Type    | Description                                                                                                                                      |

| \--------------- | \------- | \------------------------------------------------------------------------------------------------------------------------------------------------ |

| Account         | String  | References the Account ID, i.e. U1234567, being allocated to.                                                                                    |

| Position        | Decimal | References the current position of the account being allocated to.                                                                               |

| PositionDesired | Decimal | States the full position increase intended by the current trade.                                                                                 |

| PosiionAfter    | Decimal | References the increase to position from the current trade. Unless the order is partially filled, this should reflect the PositionDesired value. |

| DesiredAllocQty | Decimal | Reference the quantity to increase by based on allocation.                                                                                       |

| AllowedAllocQty | Decimal | References the maximum allowed quantity increase.                                                                                                |

| IsMonetary      | Boolean | Denotes whether the order is a monetary allocation (true) or whole share allocation (false).                                                     |

&nbsp;

\---

&nbsp;

\#\# title: OrderCancel Class Reference

&nbsp;

The Order cancellation parameters when cancelling an order.

&nbsp;

| Name                  | Type   | Description                                                                                                                                                                                       |

| \--------------------- | \------ | \------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| extOperator           | string | Following \[CME Rule 576\](https://www.cmegroup.com/rulebook/files/cme-group-Rule-576.pdf), the ExtOperator field will signify the unique API operator at the time of trading for order management. |

| manualOrderIndicator  | int    | Following \[CME Rule 576\](https://www.cmegroup.com/rulebook/files/cme-group-Rule-576.pdf), the ManualOrderIndicator field will signify if an order is manual (1) or automated (0).                 |

| manualOrderCancelTime | string | Used by brokers and advisors when manually entering an order cancellation request. Format should be "YYYYMMDD-HH:mm:ss" using UTC as the timezone value.                                          |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Allows to specify a price on an order's leg.

&nbsp;

| Name  | Type   | Description            |

| \----- | \------ | \---------------------- |

| Price | double | The order leg's price. |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                            | Type          | Description |

| \------------------------------- | \------------- | \----------- |

| OrderComboLeg (double p\\\_price) | override bool |             |

| GetHashCode ()                  | override int  |             |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Provides an active order's current state.

&nbsp;

| Name                           | Type   | Description                                                                                                        |

| \------------------------------ | \------ | \------------------------------------------------------------------------------------------------------------------ |

| Status                         | string | The order's current status.                                                                                        |

| InitMarginBefore               | string | The account's current initial margin.                                                                              |

| MaintMarginBefore              | string | The account's current maintenance margin.                                                                          |

| EquityWithLoanBefore           | string | The account's current equity with loan.                                                                            |

| InitMarginChange               | string | The change of the account's initial margin.                                                                        |

| MaintMarginChange              | string | The change of the account's maintenance margin.                                                                    |

| EquityWithLoanChange           | string | The change of the account's equity with loan.                                                                      |

| InitMarginAfter                | string | The order's impact on the account's initial margin.                                                                |

| MaintMarginAfter               | string | The order's impact on the account's maintenance margin.                                                            |

| EquityWithLoanAfter            | string | Shows the impact the order would have on the account's equity with loan.                                           |

| InitMarginBeforeOutsideRTH     | float  | The account's expected initial margin outside of regular trading hours.                                            |

| MaintMarginBeforeOutsideRTH    | float  | The account's expected maintenance margin outside of regular trading hours.                                        |

| EquityWithLoanBeforeOutsideRTH | float  | The account's expected equity with loan outside of regular trading hours.                                          |

| InitMarginChangeOutsideRTH     | float  | The expected change of the account's initial margin outside of regular trading hours.                              |

| MaintMarginChangeOutsideRTH    | float  | The expected change of the account's maintenance margin outside of regular trading hours.                          |

| EquityWithLoanChangeOutsideRTH | float  | The expected change of the account's equity with loan outside of regular trading hours.                            |

| InitMarginAfterOutsideRTH      | float  | The order's expected impact on the account's initial margin outside of regular trading hours.                      |

| MaintMarginAfterOutsideRTH     | float  | The order's expected impact on the account's maintenance margin outside of regular trading hours.                  |

| EquityWithLoanAfterOutsideRTH  | float  | Shows the expected impact the order would have on the account's equity with loan outside of regular trading hours. |

| Commission                     | double | The order's generated commission.                                                                                  |

| MinCommission                  | double | The execution's minimum commission.                                                                                |

| MaxCommission                  | double | The executions maximum commission.                                                                                 |

| CommissionCurrency             | string | The generated commission currency.                                                                                 |

| WarningText                    | string | If the order is warranted, a descriptive message will be provided.                                                 |

| CompletedTime                  | string |                                                                                                                    |

| CompletedStatus                | string |                                                                                                                    |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                                                                                                                                                                                                                                                                                                                                                                                                                                | Type          | Description |

| \----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | \------------- | \----------- |

| OrderState (string status, string initMarginBefore, string maintMarginBefore, string equityWithLoanBefore, string initMarginChange, string maintMarginChange, string equityWithLoanChange, string initMarginAfter, string maintMarginAfter, string equityWithLoanAfter, double commission, double minCommission, double maxCommission, string commissionCurrency, string warningText, string completedTime, string completedStatus) | override bool |             |

| Equals (object obj)                                                                                                                                                                                                                                                                                                                                                                                                                 | override bool |             |

| GetHashCode ()                                                                                                                                                                                                                                                                                                                                                                                                                      | override int  |             |

&nbsp;

\---

&nbsp;

\#\# title: PercentChangeCondition Class Reference

&nbsp;

Used with conditional orders to place or submit an order based on a percentage change of an instrument to the last close price.

&nbsp;

| Name          | Type            | Description                                              |

| \------------- | \--------------- | \-------------------------------------------------------- |

| Value         | override string |                                                          |

| ChangePercent | double          | Percentage Change field used in conditional order logic. |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Used with conditional orders to cancel or submit order based on price of an instrument.

&nbsp;

| Name          | Type            | Description                                  |

| \------------- | \--------------- | \-------------------------------------------- |

| Value         | override string |                                              |

| Price         | string          | Price field used in conditional order logic. |

| TriggerMethod | TriggerMethod   |                                              |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                               | Type            | Description                |

| \---------------------------------- | \--------------- | \-------------------------- |

| ToString()                         | override string | Returns string to display. |

| Equals (object obj)                | override bool   |                            |

| GetHashCode ()                     | override int    |                            |

| Deserialize (IDecoder inStream)    | override void   |                            |

| Serialize (BinaryWriter outStream) | override void   |                            |

&nbsp;

\---

&nbsp;

\#\# title: Protected Member Functions

&nbsp;

| Name                  | Type          | Description                                    |

| \--------------------- | \------------- | \---------------------------------------------- |

| TryParse(string cond) | override bool | Validates the price condition format is valid. |

&nbsp;

\---

&nbsp;

\#\# title: ScannerSubscription Class Reference

&nbsp;

Defines a market scanner request.

&nbsp;

| Name                     | Type   | Description                                                                                                                                                                                                   |

| \------------------------ | \------ | \------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| NumberOfRows             | int    | Determine the number of rows or results from the market scanner to be returned. Returns the maximum, 50, by default.                                                                                          |

| Instrument               | string | Returns the Instrument type to be returned. See scannerParameters xml response for details.                                                                                                                   |

| LocationCode             | string | Returns the exchange regions to be returned. See scannerParameters xml response for details.                                                                                                                  |

| ScanCode                 | string | Returns the code to sort results by. See scannerParameters xml response for details.                                                                                                                          |

| AbovePrice               | double | Set the maximum MARK price to filter by.                                                                                                                                                                      |

| BelowPrice               | double | Set the minimum MARK price to filter by.                                                                                                                                                                      |

| AboveVolume              | int    | Set the minimum trade volume of the day.                                                                                                                                                                      |

| AverageOptionVolumeAbove | int    | Determine the minimum average option volume from the underlying.                                                                                                                                              |

| MarketCapAbove           | double | Set the minimum market cap restriction.                                                                                                                                                                       |

| MarketCapBelow           | double | Set the maximum market cap restriction.                                                                                                                                                                       |

| MoodyRatingAbove         | string | Minimum Moody Rating                                                                                                                                                                                          |

| MoodyRatingBelow         | string | Maximum Moody Rating                                                                                                                                                                                          |

| SpRatingAbove            | string | Standard & Poor's (S\\\&P) uses a letter-based rating system to evaluate the creditworthiness of bonds and debt issuers. This field will indicate the lowest acceptable rating to be returned from the result.  |

| SpRatingBelow            | string | Standard & Poor's (S\\\&P) uses a letter-based rating system to evaluate the creditworthiness of bonds and debt issuers. This field will indicate the highest acceptable rating to be returned from the result. |

| MaturityDateAbove        | string | Set the minimum Maturity date. Formatted as YYYYMMDD.                                                                                                                                                         |

| MaturityDateBelow        | string | Set the maximum Maturity date. Formatted as YYYYMMDD.                                                                                                                                                         |

| CouponRateAbove          | double |                                                                                                                                                                                                               |

&nbsp;

Set the minimum Coupon Rate

&nbsp;

|

\\| CouponRateBelow | double |

&nbsp;

Set the maximum Coupon Rate

&nbsp;

|

\\| ExcludeConvertible | bool | Determine of the bond should be convertible or not. |

\\| ScannerSettingPairs | string | TagValue pair to indicate scanner restrictions. Currently only supports TagValue("annualVolatility", true) or an empty list. |

\\| StockTypeFilter | string | Determine the stock type: Common, CORP, ADR, ETF, ETN, REIT, CEF, ETMF, EFN |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

A container for storing Soft Dollar Tier information.

&nbsp;

| Name        | Type   | Description                               |

| \----------- | \------ | \----------------------------------------- |

| Name        | string | The name of the Soft Dollar Tier.         |

| Value       | string | The value of the Soft Dollar Tier.        |

| DisplayName | string | The display name of the Soft Dollar Tier. |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                | Type            | Description                |

| \------------------- | \--------------- | \-------------------------- |

| Equals (object obj) | override bool   |                            |

| GetHashCode ()      | override int    |                            |

| ToString()          | override string | Returns string to display. |

&nbsp;

\---

&nbsp;

\#\# title: Static Public Member Functions

&nbsp;

| Name                            | Type                               | Description |

| \------------------------------- | \---------------------------------- | \----------- |

| operator== (SoftDollarTier left | static bool, SoftDollarTier right) |             |

| operator\!= (SoftDollarTier left | static bool, SoftDollarTier right) |             |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Convenience class to define key-value pairs.

&nbsp;

| Name  | Type   | Description |

| \----- | \------ | \----------- |

| Tag   | string |             |

| Value | string |             |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Convenience class to define key-value pairs.

&nbsp;

| Name  | Type   | Description |

| \----- | \------ | \----------- |

| Tag   | string |             |

| Value | string |             |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Convenience class to define key-value pairs.

&nbsp;

| Name  | Type   | Description |

| \----- | \------ | \----------- |

| Tag   | string |             |

| Value | string |             |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name                  | Type          | Description |

| \--------------------- | \------------- | \----------- |

| Equals (object other) | override bool |             |

| GetHashCode ()        | override int  |             |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Tick attributes that describes additional information for price ticks

&nbsp;

| Name           | Type | Description                                                                                                                            |

| \-------------- | \---- | \-------------------------------------------------------------------------------------------------------------------------------------- |

| CanAutoExecute | bool | Used with tickPrice callback from reqMktData. Specifies whether the price tick is available for automatic execution (1) or not (0).    |

| PastLimit      | bool | Used with tickPrice to indicate if the bid price is lower than the day's lowest value or the ask price is higher than the highest ask. |

| PreOpen        | bool | Indicates whether the bid/ask price tick is from pre-open session.                                                                     |

| Unreported     | bool | Used with tick-by-tick data to indicate if a trade is classified as 'unreportable' (odd lots                                           |

| BidPastLow     | bool | Used with real time tick-by-tick. Indicates if bid is lower than day's lowest low.                                                     |

| AskPastHigh    | bool | Used with real time tick-by-tick. Indicates if ask is higher than day's highest ask.                                                   |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name       | Type            | Description                |

| \---------- | \--------------- | \-------------------------- |

| ToString() | override string | Returns string to display. |

&nbsp;

\---

&nbsp;

\#\# title: Introduction

&nbsp;

Time condition used in conditional orders to submit or cancel orders at specified time.

&nbsp;

| Name  | Type            | Description                                                                  |

| \----- | \--------------- | \---------------------------------------------------------------------------- |

| Value | override string |                                                                              |

| Time  | string          | Time field used in conditional order logic. Valid format: YYYYMMDD HH:MM:SS. |

&nbsp;

\---

&nbsp;

\#\# title: Public Member Functions

&nbsp;

| Name       | Type            | Description                |

| \---------- | \--------------- | \-------------------------- |

| ToString() | override string | Returns string to display. |

&nbsp;

\---

&nbsp;

\#\# title: VolumeCondition Class Reference

&nbsp;

Used with conditional orders to submit or cancel an order based on a specified volume change in a security.

&nbsp;

| Name   | Type            | Description |

| \------ | \--------------- | \----------- |

| Value  | override string |             |

| Volume | int             |             |

&nbsp;

\---

&nbsp;

\#\# title: WshEventData Class Reference

&nbsp;

Class used to define the parameters for the EClient::reqWshEventData query to filter results.

&nbsp;

| Name            | Type    | Description                                                                                                                                                                                                                                        |

| \--------------- | \------- | \-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| ConId           | int     | Contract identifier used to specify an unique contract                                                                                                                                                                                             |

| Filter          | string  | A JSON formatted string containing a minimum of string Country, and array watchlist tags. In addition, a unique filter may be specified as "true" in order to receive a specific filter. Filter values are returned from the wshMetaData function. |

| FillWatchlist   | boolean | Defines                                                                                                                                                                                                                                            |

| FillPortfolio   | boolean |                                                                                                                                                                                                                                                    |

| FillCompetitors | boolean |                                                                                                                                                                                                                                                    |

| StartDate       | string  |                                                                                                                                                                                                                                                    |

&nbsp;

The beginning of your request formatting. Values should be represented like "YYYYMMDD".

&nbsp;

\\| EndDate | string | The end of your request formatting. Values should be represented like "YYYYMMDD". |

\\| TotalLimit | int | Specify the maximum number of results that can be returned. A maximum of |

&nbsp;

\---

&nbsp;

\#\# title: Understanding Message Codes

&nbsp;

The TWS uses the \[EWrapper.error\](/tws-api/doc/error-handling/receiving-error-messages) method not only to deliver errors but also warnings or informative messages. This is done mostly for simplicity's sake. Below is a table with all the messages which can be sent by the TWS/IB Gateway. All messages delivered by the TWS are usually accompanied by a brief but meaningful description pointing in the direction of the problem.

&nbsp;

Remember that the TWS API simply connects to a running TWS/IB Gateway which most of times will be running on your local network if not in the same host as the client application. It is your responsibility to provide reliable connectivity between the TWS and your client application.

&nbsp;

\---

&nbsp;

\#\# title: System Message Codes

&nbsp;

The messages in the table below are not a consequence of any action performed by the client application. They are notifications about the connectivity status between the TWS and our servers. Your client application must pay special attention to them and handle the situation accordingly. You are very likely to loose connectivity to our servers at least once a day due to our daily server maintenance downtime as clearly detailed in our Current System Status page. Note that after the system reset, the TWS/IB Gateway will automatically reconnect to our servers and you can resume your operations normally.

&nbsp;

Important: during a reset period, there may be an interruption in the ability to log in or manage orders. Existing orders (native types) will operate normally although execution reports and simulated orders will be delayed until the reset is complete. It is not recommended to operate during the scheduled reset times.

&nbsp;

| Code | TWS message                                                                                                          | Additional notes                                                                                                                                                                |

| \---- | \-------------------------------------------------------------------------------------------------------------------- | \------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| 1100 | Connectivity between IB and the TWS has been lost.                                                                   | Your TWS/IB Gateway has been disconnected from IB servers. This can occur because of an internet connectivity issue, a nightly reset of the IB servers, or a competing session. |

| 1101 | Connectivity between IB and TWS has been restored- data lost.\\\*                                                      | The TWS/IB Gateway has successfully reconnected to IB's s---

&nbsp;

\#\# title: System Message Codes

&nbsp;

The messages in the table below are not a consequence of any action performed by the client application. They are notifications about the connectivity status between the TWS and our servers. Your client application must pay special attention to them and handle the situation accordingly. You are very likely to loose connectivity to our servers at least once a day due to our daily server maintenance downtime as clearly detailed in our Current System Status page. Note that after the system reset, the TWS/IB Gateway will automatically reconnect to our servers and you can resume your operations normally.

&nbsp;

Important: during a reset period, there may be an interruption in the ability to log in or manage orders. Existing orders (native types) will operate normally although execution reports and simulated orders will be delayed until the reset is complete. It is not recommended to operate during the scheduled reset times.

&nbsp;

| Code | TWS message                                                                                                          | Additional notes                                                                                                                                                                |

| \---- | \-------------------------------------------------------------------------------------------------------------------- | \------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

| 1100 | Connectivity between IB and the TWS has been lost.                                                                   | Your TWS/IB Gateway has been disconnected from IB servers. This can occur because of an internet connectivity issue, a nightly reset of the IB servers, or a competing session. |

| 1101 | Connectivity between IB and TWS has been restored- data lost.\\\*                                                      | The TWS/IB Gateway has successfully reconnected to IB's servers. Your market data requests have been lost and need to be re-submitted.                                          |

| 1102 | Connectivity between IB and TWS has been restored- data maintained.                                                  | The TWS/IB Gateway has successfully reconnected to IB's servers. Your market data requests have been recovered and there is no need for you to re-submit them.                  |

| 1300 | TWS socket port has been reset and this connection is being dropped. Please reconnect on the new port – \\\<port\\\_num\> | The port number in the TWS/IBG settings has been changed during an active API connection.                                                                                       |

&nbsp;

ervers. Your market data requests have been lost and need to be re-submitted.                                          |

| 1102 | Connectivity between IB and TWS has been restored- data maintained.                                                  | The TWS/IB Gateway has successfully reconnected to IB's servers. Your market data requests have been recovered and there is no need for you to re-submit them.                  |

| 1300 | TWS socket port has been reset and this connection is being dropped. Please reconnect on the new port – \\\<port\\\_num\> | The port number in the TWS/IBG settings has been changed during an active API connection.                                                                                       |

&nbsp;

&nbsp;