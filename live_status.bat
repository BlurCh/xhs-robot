@echo off
REM Check creator login state without opening a window.
cd /d "%~dp0"
".venv\Scripts\python.exe" cli.py live status
pause
