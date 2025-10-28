#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Single process IB worker for testing"""

import force_utf8
import sys
sys.path.insert(0, r'F:\Cursor\chanlun\src')

print("Testing single IB worker...")

# Import directly
import datetime
import json
import time
import ib_insync
import pandas as pd
import pytz

from chanlun import config, fun, rd
from chanlun.base import Market
from chanlun.exchange.exchange_ib import CmdEnum, ib_res_hkey
from chanlun.file_db import FileCacheDB

print("Imports OK")
print(f"IB Gateway: {config.IB_HOST}:{config.IB_PORT}")

# Test basic connection
ib = ib_insync.IB()
print("Connecting to IB Gateway...")
ib.connect(config.IB_HOST, config.IB_PORT, clientId=999, timeout=30, readonly=True)
print("Connected!")

# Test getting some data
contract = ib_insync.Stock(symbol='AAPL', exchange='SMART', currency='USD')
print("Requesting AAPL data...")
bars = ib.reqHistoricalData(
    contract,
    endDateTime='',
    durationStr='1 D',
    barSizeSetting='5 mins',
    whatToShow='TRADES',
    useRTH=True,
    formatDate=1,
    timeout=20
)
print(f"Received {len(bars)} bars")
if len(bars) > 0:
    print(f"Latest: {bars[-1]}")
    print("\n[SUCCESS] Basic IB worker functionality verified!")
else:
    print("\n[FAIL] No data received")

ib.disconnect()
print("\nTest complete")


