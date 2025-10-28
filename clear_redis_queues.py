#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\Cursor\chanlun\src')

from chanlun import rd
from chanlun.exchange.exchange_ib import CmdEnum, ib_res_hkey

# Clear all IB command queues
queues_cleared = []
for cmd in [
    CmdEnum.SEARCH_STOCKS,
    CmdEnum.KLINES,
    CmdEnum.TICKS,
    CmdEnum.STOCK_INFO,
    CmdEnum.BALANCE,
    CmdEnum.POSITIONS,
    CmdEnum.ORDERS,
]:
    count = rd.Robj().delete(cmd.value)
    queues_cleared.append(f"{cmd.value}: {count}")
    print(f"Cleared {cmd.value}: {count} items")

# Clear all result keys
h_keys = rd.Robj().keys(f"{ib_res_hkey}*")
for k in h_keys:
    rd.Robj().delete(k)
print(f"Cleared {len(h_keys)} result keys")

print("\nRedis queues cleaned successfully!")


