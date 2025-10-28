#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'F:\Cursor\chanlun\src')

try:
    from chanlun import config
    print("SUCCESS: chanlun module imported")
    print(f"IB_HOST: {config.IB_HOST}")
    print(f"IB_PORT: {config.IB_PORT}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()


