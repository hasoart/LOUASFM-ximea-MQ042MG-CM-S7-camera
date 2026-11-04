@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create the venv first. See README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m louasfm_camera %*
if errorlevel 1 pause
