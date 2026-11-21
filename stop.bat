@echo off
rem Double-click me to stop the collector, fetcher, clicker and transcriber.
wmic process where "name='python.exe' and commandline like '%%collector.py%%'" delete >nul 2>&1
wmic process where "name='python.exe' and commandline like '%%file_fetcher.py%%'" delete >nul 2>&1
wmic process where "name='python.exe' and commandline like '%%file_clicker.py%%'" delete >nul 2>&1
wmic process where "name='python.exe' and commandline like '%%voice_transcriber.py%%'" delete >nul 2>&1
echo All components stopped.
pause
