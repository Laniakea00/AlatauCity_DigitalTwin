@echo off
rem Alatau City: check the WebGL build in Chrome on this computer (see check_build_windows.ps1)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_build_windows.ps1" %*
echo.
pause
