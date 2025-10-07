@echo off
echo ========================================
echo Starting Automated Trading System
echo ========================================
echo.

REM Activate virtual environment
if exist venv (
    call venv\Scripts\activate
) else (
    echo ERROR: Virtual environment not found!
    echo Please run install.bat first
    pause
    exit /b 1
)

echo Starting in development mode...
python main.py --env development --verbose

pause