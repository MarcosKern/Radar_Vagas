@echo off
cd /d "%~dp0"
where py >nul 2>&1
if %ERRORLEVEL%==0 (set "PY=py -3") else (set "PY=python")
start "" "http://127.0.0.1:8765/"
%PY% monitor.py serve
if errorlevel 1 (echo Verifique se Python 3.11+ esta instalado. & pause)
