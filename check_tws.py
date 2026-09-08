from ibkr_env import require_ib_async

require_ib_async()   # names the interpreter, not just the module
from ib_async import IB, Stock
ib = IB(); ib.connect('127.0.0.1', 7497, clientId=99, timeout=20)
print('connected:', ib.isConnected())
c = ib.qualifyContracts(Stock('SOXL', 'SMART', 'USD', primaryExchange='ARCA'))[0]
print('conId:', c.conId)
print([v.value for v in ib.accountValues() if v.tag == 'NetLiquidation'][:1])
ib.disconnect()