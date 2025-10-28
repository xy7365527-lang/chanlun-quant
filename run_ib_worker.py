#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""IB Worker with UTF-8 encoding fix"""

# MUST import this first to fix encoding
import force_utf8

import sys
import os

sys.path.insert(0, r'F:\Cursor\chanlun\src')
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Now import and run the actual script
if __name__ == "__main__":
    print("Starting IB Tasks Worker...")
    try:
        # Import the fixed version that uses Process instead of ProcessPoolExecutor
        import runpy
        runpy.run_module('script.crontab.script_ib_tasks_fixed', run_name='__main__')
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        import time
        time.sleep(60)  # Keep window open for 60 seconds

