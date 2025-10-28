#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""IB Tasks Launcher with proper PYTHONPATH"""
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / 'src'
if src_path.exists():
    sys.path.insert(0, str(src_path))

# Now run the actual script
if __name__ == "__main__":
    from script.crontab import script_ib_tasks
    # The script will run its main block


