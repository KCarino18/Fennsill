@echo off
title Artiphact Setup
cd /d "%~dp0"
echo Installing Artiphact from the panel...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL.PS1"
if errorlevel 1 pause
