@echo off
chcp 65001 >nul
set PYTHONPATH=F:\Cursor\chanlun\src
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d F:\Cursor\chanlun
echo Starting IB Tasks with Python 3.11...
echo PYTHONPATH=%PYTHONPATH%
C:\Users\hanju\AppData\Local\Python\pythoncore-3.11-64\python.exe -m script.crontab.script_ib_tasks
pause

