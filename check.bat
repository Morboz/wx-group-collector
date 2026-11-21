@echo off
chcp 65001 >nul
rem Double-click me to check collector health.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check-status.ps1"
