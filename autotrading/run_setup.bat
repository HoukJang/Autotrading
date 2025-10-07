@echo off
echo ========================================
echo Trading System Setup Script
echo ========================================
echo.

REM Check if venv exists
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip -q

REM Install requirements
echo Installing requirements...
pip install -r requirements.txt -q

echo.
echo ========================================
echo Setup Database
echo ========================================
echo.

REM Run database setup
python scripts\setup_database_clean.py

echo.
echo ========================================
echo Setup complete!
echo ========================================
pause