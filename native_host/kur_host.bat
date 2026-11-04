@echo off
rem Kami tarayici koprusunu Brave + Chrome + Edge icin kaydeder (sadece bu kullanici, yonetici gerekmez).
rem Kaldirmak icin: kur_host.bat kaldir
setlocal
set "PY=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo .venv bulunamadi. Once proje klasorunde "uv sync" calistirin.
  pause
  exit /b 1
)
if /i "%~1"=="kaldir" (
  "%PY%" "%~dp0install.py" --remove
) else (
  "%PY%" "%~dp0install.py"
)
echo.
pause
