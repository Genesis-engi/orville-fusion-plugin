@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "INSTALLER=%SCRIPT_DIR%scripts\install-windows.ps1"

if not exist "%INSTALLER%" (
  echo Installer script not found:
  echo   %INSTALLER%
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%INSTALLER%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo Orville Fusion Plugin installer finished.
  echo Launch Autodesk Fusion, then open Utilities ^> Add-Ins ^> Scripts and Add-Ins.
) else (
  echo Orville Fusion Plugin installer failed with exit code %EXIT_CODE%.
)
echo.
pause
exit /b %EXIT_CODE%
