@echo off
cd /d "%~dp0"
title Artiphact Factory
if exist "ArtiphactFactory.exe" (
  start "" "%~dp0ArtiphactFactory.exe"
  exit /b 0
)
echo ArtiphactFactory.exe not built yet.
echo Building it now...
call "%~dp0Build-Factory-Exe.bat"
if exist "ArtiphactFactory.exe" (
  start "" "%~dp0ArtiphactFactory.exe"
  exit /b 0
)
echo Build failed.
pause
