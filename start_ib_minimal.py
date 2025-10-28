#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Minimal IB Tasks starter - bypasses frozen module issues"""
import sys
import os
sys.path.insert(0, r'F:\Cursor\chanlun\src')
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Test imports first
try:
    import ib_insync
    import pandas as pd
    import pytz
    print("Core libs OK")
    
    # Try importing the IB tasks module WITHOUT running it
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "script_ib_tasks", 
        r"F:\Cursor\chanlun\script\crontab\script_ib_tasks.py"
    )
    module = importlib.util.module_from_spec(spec)
    
    # Execute the module (will run __main__ block)
    spec.loader.exec_module(module)
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    input("Press Enter to exit...")


