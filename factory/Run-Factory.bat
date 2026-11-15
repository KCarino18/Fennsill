@echo off
cd /d "%~dp0"
title Fennsill Factory
if exist "FennsillFactory.exe" (
  start "" "%~dp0FennsillFactory.exe"
  exit /b 0
)
echo FennsillFactory.exe not built yet.
echo Building it now...
call "%~dp0Build-Factory-Exe.bat"
if exist "FennsillFactory.exe" (
  start "" "%~dp0FennsillFactory.exe"
  exit /b 0
)
echo Build failed.
pause
