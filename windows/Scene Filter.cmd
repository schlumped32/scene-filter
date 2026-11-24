@echo off
rem Scene Filter for Windows: double-click to start. This window is the app: keep it open, close it to quit.
title Scene Filter
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\launcher.ps1"
if errorlevel 1 (
  echo.
  echo Scene Filter stopped with a problem. The details above will help fix it.
  pause
)
