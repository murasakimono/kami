@echo off
rem Magnet_Kaydet.bat'in yaptigini geri alir: HKCU\Software\Classes\magnet silinir.
rem (Bu kayit Kami'den once YOKTU; baska uygulamanin kaydina dokunulmaz.)
reg query "HKCU\Software\Classes\magnet\shell\open\command" /ve 2>nul | find /i "kami_open.pyw" >nul
if errorlevel 1 (
  echo Kami'nin magnet kaydi bulunamadi; bir sey degistirilmedi.
) else (
  reg delete "HKCU\Software\Classes\magnet" /f >nul
  echo Kami'nin magnet kaydi kaldirildi.
)
pause
