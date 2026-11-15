@echo off
cd /d "%~dp0\.."
title Build ArtiphactFactory.exe
echo Building ArtiphactFactory.exe ...
dotnet publish artiphact-factory\ArtiphactFactory.csproj -c Release -o factory
if errorlevel 1 (
  echo Build failed. Install .NET SDK.
  pause
  exit /b 1
)
echo.
echo Done: factory\ArtiphactFactory.exe
echo Double-click that to open the window.
echo.
pause
