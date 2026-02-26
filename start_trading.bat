@echo off
title AutoTrader v2 - Live Trading
cd /d "%~dp0"

echo ==========================================
echo   AutoTrader v2 - Paper Trading
echo ==========================================
echo.
echo Starting AutoTrader + Live Dashboard...
echo.

:: Start Dashboard in a new window
start "AutoTrader Dashboard" cmd /c "python scripts/run_live_dashboard.py"

:: Wait 2 seconds for dashboard to start
timeout /t 2 /nobreak >nul

:: Run AutoTrader in this window (keeps it alive)
echo AutoTrader is running. Close this window to stop.
echo Dashboard: http://localhost:8501
echo.
python -m autotrader.main

:: If AutoTrader exits, pause so user can see errors
echo.
echo AutoTrader has stopped.
pause
