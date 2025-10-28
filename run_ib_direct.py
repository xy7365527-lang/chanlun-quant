#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Direct IB Tasks Runner with detailed logging"""
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

print(f"Python path: {sys.path[:3]}")
print(f"Starting IB Tasks...")

try:
    # Import and run directly
    import script.crontab.script_ib_tasks as ibt
    print("Module imported successfully")
    print("Script file:", ibt.__file__)
    
except Exception as e:
    print(f"ERROR during import: {e}")
    import traceback
    traceback.print_exc()


