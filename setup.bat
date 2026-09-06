@echo off
REM One-time setup on a machine that can reach xiaohongshu.
REM Creates .venv, installs requirements and Playwright Chromium.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
".venv\Scripts\python.exe" -m playwright install chromium
echo.
echo Setup done. Now run live_login.bat and scan the QR code once.
pause
