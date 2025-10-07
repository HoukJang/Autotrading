@echo off
echo ========================================
echo Phase 1 Infrastructure Test
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

echo Running Phase 1 tests...
python scripts\test_phase1.py

echo.
pause