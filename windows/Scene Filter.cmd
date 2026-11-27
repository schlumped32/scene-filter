@echo off
setlocal
rem Scene Filter for Windows: double-click to start. This window is the app: keep it open, close it to quit.
title Scene Filter
if not exist "%~dp0app\launcher.ps1" goto :nofiles
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\launcher.ps1"
set "CODE=%ERRORLEVEL%"
if "%CODE%"=="0" exit /b 0
echo.
echo Scene Filter stopped with a problem, code %CODE%.
echo The details above will help fix it. A copy is saved in:
echo   %LOCALAPPDATA%\Scene Filter\scene-filter.log
echo.
pause
exit /b %CODE%

:nofiles
echo Scene Filter can't find its files.
echo.
echo This usually means it was opened from inside the zip file. To fix it:
echo   1. Close this window.
echo   2. Right-click the downloaded zip and choose "Extract All...".
echo   3. Open the extracted "Scene Filter for Windows" folder and double-click Scene Filter there.
echo.
pause
exit /b 1
