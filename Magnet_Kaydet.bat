@echo off
rem Kami'yi Windows'ta magnet: linklerinin isleyicisi yapar (sadece bu kullanici, HKCU; yonetici gerekmez).
rem Geri almak icin: Magnet_Geri_Al.bat
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo .venv bulunamadi. Bu klasorde once "uv sync" calistirin.
  pause
  exit /b 1
)
set "PYW=%~dp0.venv\Scripts\pythonw.exe"
set "OPEN=%~dp0kami_open.pyw"
reg add "HKCU\Software\Classes\magnet" /ve /d "URL:Magnet Protocol" /f >nul
reg add "HKCU\Software\Classes\magnet" /v "URL Protocol" /d "" /f >nul
reg add "HKCU\Software\Classes\magnet\DefaultIcon" /ve /d "\"%PYW%\",0" /f >nul
reg add "HKCU\Software\Classes\magnet\shell\open\command" /ve /d "\"%PYW%\" \"%OPEN%\" --magnet \"%%1\"" /f >nul
if errorlevel 1 (
  echo Kayit BASARISIZ.
) else (
  echo Kami artik magnet: linklerini aciyor ^(Real-Debrid'e gonderir^).
  echo Tarayici ilk seferde "Kami ile acilsin mi?" diye sorabilir.
)
pause
