@echo off
cd /d "%~dp0"
title Artiphact Factory — FLASH
echo.
echo  Plug in ONE Artiphact e-ink panel (XIAO), then press any key.
echo  Random COM / CH340 / Arduino boards will be refused.
echo  (Or close this window to cancel.)
echo.
pause >nul
python ArtiphactFactory.py --flash
echo.
if errorlevel 1 (
  echo FLASH failed.
  pause
  exit /b 1
)
echo Done. Press any key to close.
pause >nul
