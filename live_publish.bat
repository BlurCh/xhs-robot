@echo off
REM Publish the finalized draft of a day.
REM Usage: live_publish.bat            (publish today)
REM        live_publish.bat 2026-09-06
cd /d "%~dp0"
if "%~1"=="" (
  ".venv\Scripts\python.exe" cli.py live publish
) else (
  ".venv\Scripts\python.exe" cli.py live publish --day %~1
)
pause
