@echo off
chcp 65001 >nul
rem Double-click me to start collecting WeChat group messages.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-collector.ps1"
