@echo off
REM One-click downloader (resumable) for ComfyUI + SDXL/IPAdapter models.
REM Usage:  setup_comfy.bat comfy | models | all   (default all)
REM Models end up in comfyui\ComfyUI_windows_portable\ComfyUI\models\
REM NOTE: ComfyUI server must be stopped before re-extracting the 7z.
cd /d "%~dp0"
set HUB=huggingface.co
".venv\Scripts\python.exe" downloads_comfy.py %~1
if %ERRORLEVEL% NEQ 0 (
  echo.
  echo Download interrupted. Re-run this bat to resume from where it stopped.
  pause
  exit /b %ERRORLEVEL%
)
echo.
echo Downloads done. Placing model files...
powershell -NoProfile -Command "$ErrorActionPreference='Continue'; $root='C:\Harness_Projects\xhs-robot\comfyui'; if (-not (Test-Path \"$root\ComfyUI_windows_portable\python_embeded\")) { Write-Output 'extracting base...'; & 'C:\Program Files\7-Zip\7z.exe' x -y -o\"$root\" \"$root\downloads\comfyui.7z\" | Out-Null } else { Write-Output 'base already present, skip re-extract' }; Copy-Item -Recurse -Force \"$root\models-staging\*\" \"$root\ComfyUI_windows_portable\ComfyUI\models\"; Write-Output 'MODELS PLACED'"
pause
