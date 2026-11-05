@echo off
cd /d "%~dp0"
py -3.13 -m pip install -r requirements.txt || (pause & exit /b 1)
py -3.13 server.py
pause
