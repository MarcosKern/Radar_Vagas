@echo off
cd /d "%~dp0"
where py >nul 2>&1
if %ERRORLEVEL%==0 (set "PY=py -3") else (set "PY=python")
%PY% monitor.py scan
pause
