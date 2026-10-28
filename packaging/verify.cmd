@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify.ps1" %*
echo.
pause
