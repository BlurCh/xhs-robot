@echo off
REM Pull published notes of the currently logged-in account into .\pulls\
cd /d "%~dp0"
".venv\Scripts\python.exe" cli.py live pull
pause
