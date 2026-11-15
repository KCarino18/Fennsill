@echo off
cd /d "%~dp0"
title Fennsill Factory — FLASH
echo.
echo  Plug in ONE Fennsill e-ink panel (XIAO), then press any key.
echo  Random COM / CH340 / Arduino boards will be refused.
echo  (Or close this window to cancel.)
echo.
pause >nul
python FennsillFactory.py --flash
echo.
if errorlevel 1 (
  echo FLASH failed.
  pause
  exit /b 1
)
echo Done. Press any key to close.
pause >nul
