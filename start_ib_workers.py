#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Direct launcher for IB workers - bypasses pickle issues
"""

# MUST import this first to fix encoding
import force_utf8

import sys
import os

sys.path.insert(0, r'F:\Cursor\chanlun\src')
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Now run the script directly as a file
if __name__ == "__main__":
    print("Starting IB Tasks Worker System...")
    try:
        # Import and execute the fixed script file directly
        script_path = r'F:\Cursor\chanlun\script\crontab\script_ib_tasks_fixed.py'
        with open(script_path, encoding='utf-8') as f:
            code = compile(f.read(), script_path, 'exec')
            exec(code, {'__name__': '__main__', '__file__': script_path})
    except KeyboardInterrupt:
        print("\nCaught Ctrl+C, exiting...")
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        import time
        time.sleep(60)  # Keep window open for 60 seconds


