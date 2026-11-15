@echo off
cd /d "%~dp0\.."
title Build FennsillFactory.exe
echo Building FennsillFactory.exe ...
dotnet publish fennsill-factory\FennsillFactory.csproj -c Release -o factory
if errorlevel 1 (
  echo Build failed. Install .NET SDK.
  pause
  exit /b 1
)
echo.
echo Done: factory\FennsillFactory.exe
echo Double-click that to open the window.
echo.
pause
