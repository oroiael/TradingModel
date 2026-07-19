This engineering specification defines the architecture, data pipeline, state machine logic, and interactive broker (IBKR) execution automation for the **Asymmetric Diagonal Yield Engine** on a 3x leveraged ETF (SOXL).  
To prevent the historical backtest from generating fake alpha and to ensure seamless transition into live automated execution, the development team must build this system across three distinct, decoupled runtime layers: **Data Sanitization & Ingestion**, **The Backtest State Machine**, and **The Live IBKR Execution Gateway**.

### **Part 1: Data Ingestion & Sanitization Pipeline**

Before writing trading logic, your data pipeline must ingest and scrub two distinct historical datasets without relying on hardcoded formatting assumptions.

#### **1\. Required Datasets (By Description)**

* **Intraday Underlying Stock Price History:** A 5-minute resolution time-series dataset spanning multiple years. Essential fields include timestamps, Open, High, Low, Close, and Volume. This is required to capture the exact Monday 10:00 AM entry price and Friday 3:30 PM settlement price.  
* **Daily/Intraday Historical Option Chains:** A historical record of option contracts across all listed expirations. Essential fields include underlying timestamp, contract expiration date, strike price, option right (Call/Put), bid size, ask size, bid price, ask price, implied volatility (IV), and first-order Greeks (specifically Delta).

#### **2\. Mandatory Data Scrubbing Rules**

* **Whole-Number Strike Enforcement:** Leveraged ETFs frequently generate non-standard decimal strikes (e.g., $14.50$, $103.33$) following corporate actions or reverse stock splits. The ingestion script must hard-enforce a filter (strike % 1 \== 0) to strip out all decimal strikes before passing the chain to the pricing engine.  
* **Dynamic Timestamp Fallbacks:** Market holidays and trading halts alter standard market hours. If an exact Monday 10:00 AM bar is missing from the 5-minute underlying dataset, the pipeline must not throw a runtime exception or return None. Code a dynamic boundary lookup that automatically locks onto the **first available trading bar at or immediately following 10:00 AM** on the first active trading day of that week. Apply the identical fallback logic for Friday 3:30 PM settlement evaluation.  
* **The 20% Spread Execution Rule:** Deep out-of-the-money (OTM) or highly volatile options routinely report a Bid of $\\$0.00$ or wide bid-ask spreads. Do not use midpoint pricing. To model realistic retail execution quality, hardcode the pricing functions across all historical backtests and live execution limit orders using these formulas:

$$\\text{Price}\_{\\text{Sell}} \= \\text{Bid} \+ 0.20 \\times (\\text{Ask} \- \\text{Bid})$$  
$$\\text{Price}\_{\\text{Buy}} \= \\text{Ask} \- 0.20 \\times (\\text{Ask} \- \\text{Bid})$$  
If $\\text{Bid} \== 0.00$ or $\\text{Ask} \< \\text{Bid}$ (inverted spread), the execution engine must flag the quote as illiquid and reject the strike, searching for the next nearest valid contract.

### **Part 2: The Core Strategy Architecture**

The strategy converts a standard weekly put credit spread into a **3-Legged Asymmetric Diagonal Iron Condor** designed specifically to absorb 3x ETF volatility surges while maximizing capital efficiency.  
      UPSIDE INCOME ENGINE (Leg 3\)  
   \[Sell Weekly Call @ \~0.10 \- 0.15 Delta\] \-\> Zero additional margin required  
\=============================================================================  
                     CURRENT SOXL MARKET PRICE  
\=============================================================================  
   \[Sell Weekly Put @ \~0.20 \- 0.30 Delta\]  \-\> Primary income engine  
       DOWNSIDE INCOME ENGINE (Leg 2\)  
                         |  
                         | (Protected by)  
                         v  
   \[Buy 120-180 Day Put @ Nearest Whole Strike\] \-\> Multi-month crash anchor  
       CATASTROPHE ANCHOR (Leg 1\)

#### **Leg 1: The Long-Dated Put Anchor (Catastrophe Floor)**

Instead of buying a weekly long put that suffers from rapid, exponential time decay (Theta), the engine must purchase a long put **120 to 180 days out in expiration** at the nearest whole dollar strike to the underlying ETF's Monday morning opening price.

* **Engineering Purpose:** A multi-month put carries high Vega (sensitivity to implied volatility spikes) and decays at a fraction of the speed of a weekly put. When SOXL experiences a violent sell-off, the IV surge expands the value of this long-dated put, providing capital to fund assignment costs or execute profitable roll-ups without paying weekly execution slippage.

#### **Leg 2: The Weekly Downside Income Engine**

On Monday at 10:00 AM, sell an out-of-the-money (OTM) weekly put option expiring that Friday. Target a strike price with an option Delta between **$-0.20$ and $-0.30$** (roughly 5% to 10% below spot).

* **Engineering Purpose:** This generates your primary weekly cash flow. Because it is hedged by Leg 1, your broker only requires margin collateral equal to the strike width between Leg 2 and Leg 1, rather than cash-securing 100% of the underlying share value.

#### **Leg 3: The Asymmetric Call Overlay (Zero-Margin Yield Booster)**

Simultaneously on Monday at 10:00 AM, sell an OTM weekly call option expiring that Friday at a Delta between **$0.10$ and $0.15$**.

* **Engineering Purpose:** Because an underlying stock can only expire at one price on Friday afternoon, a portfolio cannot lose on the short call and the short put simultaneously. Standard brokerage margin rules require **zero additional collateral** to add this short call overlay against your short put. 100% of the premium collected from Leg 3 drops straight into operating cash to cushion paper losses if the put side is tested during a whipsaw.

### **Part 3: Backtest State Machine Mechanics (Phase 2\)**

The backtest engine must model the portfolio as an explicit state machine with decoupled leg accounting. Do not lump equity into a single blended metric, as this destroys audit visibility.

#### **1\. Nearest-Neighbor Strike Algorithm**

Never code exact dollar target matching (e.g., target\_strike \= round(price \* 0.95)). On high-priced or volatile ETFs, clearinghouses list strikes at variable intervals ($1, $2, $5, or $10 spacing). If the math searches for exactly $\\$137.00$ when the chain only lists $\\$135.00$ and $\\$140.00$, the script will silently fail to execute.  
The execution script must implement an Absolute Distance Nearest-Neighbor Search to lock onto the closest liquid exchange strike:  
$$\\text{Selected Strike} \= \\text{argmin}\_{i} \\left( \\vert{}\\text{ChainStrike}\_{i} \- \\text{TargetStrike}\\vert{} \\right)$$

#### **2\. Mechanical Delta Defense (The Whipsaw Roll Trigger)**

A 3x leveraged ETF cannot be modeled as a passive Monday-to-Friday hold. The engine must monitor the intraday Delta of Leg 2 (the weekly short put).

* **The State Trigger:** If a mid-week sell-off drives the short put's Delta to **$-0.50$** (meaning the option is testing the-money), the state machine must immediately trigger a defensive adjustment before Gamma acceleration widens bid-ask spreads.  
* **The Execution Logic:** The engine executes a buy-to-close order on the active weekly short put using the 20% spread formula, locking in the loss. It simultaneously executes a **roll down and out**—writing a new short put 1 to 2 weeks further out in expiration at a lower strike price. Because time value is being added, this roll must be calculated to execute for a net credit or at breakeven.

#### **3\. Decoupled Ledger Accounting Schema**

To make the backtest auditable, build a multi-column master ledger that tracks Realized Operating Cash Flow (actual cash entering/leaving the account) independently from Unrealized Paper PnL (mark-to-market contract swings) across each leg:

| Leg Ledger | Required Tracking Variables | Settlement / Exit State Logic |
| :---- | :---- | :---- |
| **Leg 1 (Anchor Put)** | Active\_Strike, DTE, Premium\_Paid, Current\_Mark\_Value | Holds across weekly cycles until DTE \<= 30 or underlying appreciates $\\ge 10\\%$, triggering a protective roll-up. |
| **Leg 2 (Short Put)** | Target\_Strike, Actual\_Strike, Premium\_Collected, Max\_Delta\_Reached | Evaluated Friday at 3:30 PM. If OTM ($\\text{Price} \> \\text{Strike}$), expires worthless; 100% premium realized. If ITM or $\\Delta \\ge 0.50$, triggers mechanical roll. |
| **Leg 3 (Short Call)** | Target\_Strike, Actual\_Strike, Premium\_Collected, Settlement\_Status | Evaluated Friday at 3:30 PM. If OTM ($\\text{Price} \< \\text{Strike}$), expires worthless; premium drops to cash. If ITM, buy to close or allow cash settlement. |
| **Account Totals** | Operating\_Cash, Sweep\_Account, Total\_Equity | Sweep 25% of net weekly realized capital gains into Sweep\_Account (capital preservation); reinvest remaining 75%. |

### **Part 4: Live IBKR Automated Execution Gateway (Phase 3\)**

To transition this logic into live trading, the software engineer must build an event-driven execution gateway connecting to Interactive Brokers via the official ibapi Python library or the asynchronous ib\_insync wrapper.

#### **1\. Atomic Spread Execution via Combo (BAG) Orders**

**Never execute multi-legged options as sequential, single-leg market or limit orders.** On an instrument as volatile as SOXL, the time delay between filling Leg 2 and Leg 3 will result in severe "legging-in" slippage, distorting your risk profile.  
All multi-leg entries and defensive rolls must be constructed and submitted as a single, atomic **Combo Order (BAG)** within IBKR:

* Define an Contract object with secType \= 'BAG', symbol \= 'SOXL', and currency \= 'USD'.  
* Append each individual option contract to the comboLegs list using ComboLeg(), explicitly designating the conId (IBKR Contract ID), ratio (1), and action ('BUY' for Leg 1; 'SELL' for Legs 2 and 3).  
* Route the order as a LMT (Limit) order set to your calculated net credit limit (Bid \+ 0.20 \* (Ask \- Bid)), ensuring the exchange fills all legs simultaneously or not at all.

#### **2\. Real-Time Greek Streaming & Roll Trigger Hook**

To automate the Mechanical Delta Defense, the live gateway cannot rely on static end-of-day data. The script must maintain an active websocket subscription to IBKR real-time market data:

* Issue reqMktData() for the active conId of Leg 2 (the short weekly put), ensuring generic tick type 106 (Option implied volatility and Greeks) is requested.  
* Attach an asynchronous event listener (client.pendingTickersEvent in ib\_insync) that continuously evaluates the live streaming Delta of the short put.  
* **The Automated Hook:** When the callback detects abs(ticker.modelGreeks.delta) \>= 0.50, the script must instantly block further order entries, cancel any resting working orders for that contract, and fire a Combo Limit Order to buy-to-close the active put and sell the next week's lower strike put.

#### **3\. State Persistence & Gateway Reconnect Logic**

Live automated execution against IBKR TWS or IB Gateway will experience socket disconnections, nightly server resets, and network interruptions. The automation script must be stateless in memory but persistent on disk:

* **The Local State Engine:** Every time a Combo Order is filled, the script must write the active trade architecture (Leg ConIDs, fill prices, entry timestamps, target expiration dates, and current cash balances) to a structured local SQLite database or JSON state file.  
* **The Reconciliation Loop:** On startup or following a socket reconnection (client.connectedEvent), the script must never assume memory is correct. It must immediately issue reqPositions() and reqOpenOrders() to query IBKR's actual clearinghouse records.  
* The script must cross-reference the live IBKR positions against the local database. If a mismatch exists (e.g., an option expired worthless over the weekend or was manually assigned), the engine must update the database state, adjust operating cash balances, and resume Delta monitoring without submitting duplicate orders.

By strictly decoupling the schema sanitization, enforcing nearest-neighbor strike selection, isolating leg accounting, and automating defensive rolls through atomic IBKR combo orders, this development architecture provides an auditable, rigorous environment to test and trade volatile leveraged ETF derivatives without structural blind spots.  
