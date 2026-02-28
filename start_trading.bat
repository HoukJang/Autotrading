@echo off
title AutoTrader v3 - Nightly Batch Architecture
cd /d "%~dp0"

echo Starting AutoTrader v3 (Nightly Batch Architecture)
echo ===================================================
echo.

REM ── Prerequisite: Python ────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo        Install Python 3.11+ and add it to your PATH, then retry.
    exit /b 1
)

REM ── Prerequisite: Config files ───────────────────────────────────────────
if not exist config\default.yaml (
    echo ERROR: Missing config\default.yaml
    exit /b 1
)
if not exist config\strategy_params.yaml (
    echo ERROR: Missing config\strategy_params.yaml
    exit /b 1
)

REM ── Prerequisite: Credentials ────────────────────────────────────────────
if not exist config\.env (
    echo WARNING: config\.env not found.  Alpaca credentials may be missing.
)

REM ── Prerequisite: Core scripts ───────────────────────────────────────────
if not exist scripts\watchdog.py (
    echo ERROR: scripts\watchdog.py not found.
    exit /b 1
)
if not exist scripts\health_check.py (
    echo ERROR: scripts\health_check.py not found.
    exit /b 1
)

REM ── Create required directories ──────────────────────────────────────────
if not exist data  mkdir data
if not exist logs  mkdir logs

REM ── Check if already running ─────────────────────────────────────────────
if exist data\watchdog.pid (
    python scripts\watchdog.py status 2>nul | findstr /C:"RUNNING" >nul 2>&1
    if not errorlevel 1 (
        echo WARNING: AutoTrader appears to be already running.
        echo          Run stop_trading.bat first, then retry.
        python scripts\watchdog.py status
        exit /b 1
    )
)

REM ── Start AutoTrader via watchdog ────────────────────────────────────────
echo [1/2] Starting AutoTrader with watchdog supervision...
start "AutoTrader Watchdog" /B python scripts\watchdog.py start

REM Give the watchdog a moment to write its PID file and launch the child.
timeout /t 3 /nobreak >nul

REM ── Start Dashboard ──────────────────────────────────────────────────────
echo [2/2] Starting Dashboard on http://localhost:8501
start "AutoTrader Dashboard" /B python -m streamlit run autotrader\dashboard\live_app.py --server.port 8501

echo.
echo ===================================================
echo   AutoTrader v3 started successfully.
echo ===================================================
echo.
echo   Trading   : watchdog-supervised process (auto-restart on crash)
echo   Dashboard : http://localhost:8501
echo   Health    : python scripts\health_check.py
echo   Logs      : logs\autotrader.log
echo   Watchdog  : logs\watchdog.log
echo   Daily log : python scripts\log_analyzer.py --save
echo.
echo   To stop   : stop_trading.bat
echo.
