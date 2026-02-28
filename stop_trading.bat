@echo off
title AutoTrader v3 - Stopping
cd /d "%~dp0"

echo Stopping AutoTrader v3...
echo ===================================================

REM ── Stop watchdog (which also terminates the autotrader child) ───────────
if exist scripts\watchdog.py (
    python scripts\watchdog.py stop
) else (
    echo WARNING: scripts\watchdog.py not found; attempting direct process kill.
    if exist data\autotrader.pid (
        set /p TRADER_PID=<data\autotrader.pid
        taskkill /PID %TRADER_PID% /F >nul 2>&1
        del /f /q data\autotrader.pid >nul 2>&1
    )
    if exist data\watchdog.pid (
        set /p WATCHDOG_PID=<data\watchdog.pid
        taskkill /PID %WATCHDOG_PID% /F >nul 2>&1
        del /f /q data\watchdog.pid >nul 2>&1
    )
)

REM ── Stop Dashboard (streamlit) ───────────────────────────────────────────
echo Stopping Dashboard...
taskkill /F /IM streamlit.exe >nul 2>&1

REM ── Close any lingering AutoTrader console windows ───────────────────────
taskkill /F /FI "WINDOWTITLE eq AutoTrader*" >nul 2>&1

echo.
echo AutoTrader v3 stopped.
echo Run 'python scripts\health_check.py' to verify all processes have exited.
echo.
