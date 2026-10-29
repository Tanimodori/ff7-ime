@echo off
rem ff7-ime uninstaller entry point.
rem
rem ASCII only on purpose: cmd.exe reads batch files in the active console
rem codepage, so non-ASCII text here would be garbled on some systems.
rem All human-readable output comes from packaging\ff7-ime.ps1 (UTF-8 + BOM).
rem
rem Options after uninstall.cmd are passed straight to the PowerShell script,
rem e.g.  uninstall.cmd -PruneSchemaList
rem        uninstall.cmd -PurgeBackups -NoDeploy
setlocal
for /f "tokens=2 delims=:" %%A in ('chcp') do set "FF7_OLDCP=%%A"
set "FF7_OLDCP=%FF7_OLDCP: =%"
chcp 65001 >nul 2>nul

set "FF7_PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%FF7_PS%" for %%I in (powershell.exe) do set "FF7_PS=%%~$PATH:I"
if not exist "%FF7_PS%" (
  echo [ff7-ime] Windows PowerShell was not found on this machine.
  echo [ff7-ime] Windows 10/11 ships PowerShell 5.1. If it is missing, run
  echo [ff7-ime]   powershell -File "%~dp0packaging\ff7-ime.ps1" -Action uninstall
  echo [ff7-ime] with whatever PowerShell you have.
  if defined FF7_OLDCP chcp %FF7_OLDCP% >nul 2>nul
  pause
  exit /b 5
)

set "FF7_PS1=%~dp0packaging\ff7-ime.ps1"
if not exist "%FF7_PS1%" (
  echo [ff7-ime] packaging\ff7-ime.ps1 is missing next to this script.
  echo [ff7-ime] Extract the whole package, then run uninstall.cmd from its root.
  if defined FF7_OLDCP chcp %FF7_OLDCP% >nul 2>nul
  pause
  exit /b 2
)

"%FF7_PS%" -NoProfile -ExecutionPolicy Bypass -File "%FF7_PS1%" -Action uninstall %*
set "FF7_RC=%ERRORLEVEL%"

echo.
if not "%FF7_RC%"=="0" echo [ff7-ime] uninstaller exited with code %FF7_RC%.

if defined FF7_OLDCP chcp %FF7_OLDCP% >nul 2>nul

set "FF7_PAUSE=1"
echo %* | findstr /i /c:"--no-pause" >nul && set "FF7_PAUSE="
if defined FF7_IME_NO_PAUSE set "FF7_PAUSE="
if defined FF7_PAUSE pause
exit /b %FF7_RC%
