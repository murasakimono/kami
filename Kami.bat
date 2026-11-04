@echo off
rem Kami'yi konsol penceresi olmadan baslatir. Zaten aciksa penceresi one gelir.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo .venv bulunamadi. Bu klasorde once "uv sync" calistirin.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m app.main
