@echo off
chcp 65001
set PYTHONPATH=F:\Cursor\chanlun\src
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d F:\Cursor\chanlun
echo Starting IB Worker in foreground...
C:\Users\hanju\AppData\Local\Python\pythoncore-3.11-64\python.exe run_ib_worker.py
echo.
echo Worker exited. Press any key to close...
pause >nul


