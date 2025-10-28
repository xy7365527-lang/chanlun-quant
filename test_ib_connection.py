#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Simple IB Gateway Connection Test"""
import ib_insync
import time

print("="*60)
print("IB Gateway Connection Test")
print("="*60)

ib = ib_insync.IB()
ib_insync.util.allowCtrlC()

# Error tracking
last_error = None

def on_error(reqId, errorCode, errorString, contract):
    global last_error
    last_error = {
        "reqId": reqId,
        "code": errorCode,
        "msg": errorString,
        "contract": repr(contract) if contract else None,
    }
    print(f"IB Error - reqId={reqId} code={errorCode} msg={errorString}")

ib.errorEvent += on_error

try:
    print("\n1. Connecting to IB Gateway at 127.0.0.1:7497...")
    ib.connect('127.0.0.1', 7497, clientId=999, timeout=60, readonly=True)
    print("   OK Connected to API!")
    
    print("\n2. Waiting for IB Gateway to connect to server farms...")
    time.sleep(8)
    
    print("\n3. Requesting historical data for AAPL (1 min bars, 3 days)...")
    contract = ib_insync.Stock(symbol='AAPL', exchange='SMART', currency='USD')
    
    last_error = None
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr='3 D',
        barSizeSetting='1 min',
        whatToShow='TRADES',
        useRTH=True,
        formatDate=1,
        timeout=20
    )
    
    print(f"   Received {len(bars)} bars")
    
    if len(bars) > 0:
        print("   [OK] Data received successfully!")
        print(f"   Latest bar: {bars[-1]}")
        print(f"\n[SUCCESS] IB Data Available!")
    else:
        print(f"   [FAIL] No data received")
        if last_error:
            print(f"   Last error: {last_error}")
        print(f"\n[FAIL] IB Data Not Available")
        
except Exception as e:
    print(f"\nError: {e}")
    import traceback
    traceback.print_exc()
finally:
    if ib.isConnected():
        ib.disconnect()
        print("\nDisconnected from IB Gateway")

