@echo off
setlocal
cd /d "%~dp0"
python main.py
if errorlevel 1 (
  echo.
  echo Could not start the game. Python 3.10+ with Tkinter is required.
  pause
)
