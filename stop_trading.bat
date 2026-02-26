@echo off
echo Stopping AutoTrader and Dashboard...
taskkill /f /fi "WINDOWTITLE eq AutoTrader*" >nul 2>&1
taskkill /f /im streamlit.exe >nul 2>&1
echo Done.
pause
