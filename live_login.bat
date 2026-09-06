@echo off
REM Open creator.xiaohongshu.com and wait for QR login (persisted in .pw-profile).
cd /d "%~dp0"
".venv\Scripts\python.exe" cli.py live login --wait-minutes 3
pause
