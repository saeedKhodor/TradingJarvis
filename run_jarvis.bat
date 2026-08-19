@echo off
chcp 65001 > nul
setlocal

:: J.A.R.V.I.S. Environment Setup
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1

echo ========================================================================
echo                 J. A. R. V. I. S.   T R A D I N G
echo           Automated Multi-Skill Telemetry & Sentinel Daemon
echo ========================================================================
echo [*] Initializing J.A.R.V.I.S. environment...
echo [*] Target Instrument: US500.cash (M1 Feed)
echo [*] Active Skills    : Safety Lock (H1/30M 9-EMA Cascade Sentinel)
echo [*] Telegram Alerts  : ENABLED (@Eltsstrategy_bot)
echo ========================================================================
echo.

:: Check for virtual environment if exists
if exist "venv\Scripts\activate.bat" (
    echo [+] Activating virtual environment...
    call venv\Scripts\activate.bat
)

:: Launch Feed Daemon
python scripts/run_feed_daemon.py --symbols US500.cash --timeframe M1 --telegram

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] J.A.R.V.I.S. daemon exited with error code %ERRORLEVEL%.
    pause
)

endlocal
