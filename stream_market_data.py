import asyncio
from ib_async import IB, Option, LimitOrder, StopOrder, util

util.patchAsyncio()

async def main():
    ib = IB()
    print("Connecting to IB Gateway on Port 4001...")
    try:
        await ib.connectAsync('127.0.0.1', 4001, clientId=1)
        
        # Define our validated SOXL option contract leg
        option_contract = Option(
            symbol='SOXL', 
            lastTradeDateOrContractMonth='20260717', 
            strike=210.0, 
            right='C', 
            exchange='SMART', 
            tradingClass='SOXL',
            multiplier='100',
            currency='USD'
        )
        await ib.qualifyContractsAsync(option_contract)

        # Allocate unique tracking IDs via the Gateway connection counter
        parent_id = ib.client.getReqId()
        take_profit_id = ib.client.getReqId()
        stop_loss_id = ib.client.getReqId()
        
        print(f"\nStructuring Linked Order Array. Parent Order ID: {parent_id}")

        # 1. The Parent Order (The Entry)
        # transmit=False tells IBKR to hold this order in memory and wait for the rest of the bracket
        parent = LimitOrder(
            action='BUY', totalQuantity=1, lmtPrice=0.10,
            orderId=parent_id, transmit=False
        )

        # 2. The Profit Taker Child Order
        # action='SELL' opposes the parent order to cleanly close the position
        take_profit = LimitOrder(
            action='SELL', totalQuantity=1, lmtPrice=5.00,
            orderId=take_profit_id, parentId=parent_id, transmit=False
        )

        # 3. The Stop Loss Child Order
        # transmit=True tells IBKR the bracket sequence is complete; transmit the bundle
        stop_loss = StopOrder(
            action='SELL', totalQuantity=1, stopPrice=0.05,
            orderId=stop_loss_id, parentId=parent_id, transmit=True
        )

        # Send the bracket to the gateway
        print("🚀 Sending linked entry and exit bracket sequence...")
        parent_trade = ib.placeOrder(option_contract, parent)
        tp_trade = ib.placeOrder(option_contract, take_profit)
        sl_trade = ib.placeOrder(option_contract, stop_loss)

        await asyncio.sleep(3)

        print("\n" + "="*50)
        print(f"📦 BRACKET TRANSMISSION REPORT")
        print("="*50)
        print(f"Parent Entry Status:      {parent_trade.orderStatus.status}")
        print(f"Child Take Profit Status: {tp_trade.orderStatus.status}")
        print(f"Child Stop Loss Status:   {sl_trade.orderStatus.status}")
        print("="*50)

        # Safety Cleanup: Canceling the parent order tears down the children automatically
        print("\nTearing down test orders from the book...")
        ib.cancelOrder(parent)
        await asyncio.sleep(1)

    except Exception as e:
        print(f"❌ Execution error: {e}")
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("Disconnected cleanly.")

if __name__ == '__main__':
    util.run(main())