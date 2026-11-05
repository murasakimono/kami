; Kami (KDM) kurulum betigi - Inno Setup 6. Derleme: uv run python packaging/build.py
; Kullanici basina kurulum (yonetici gerekmez): %LOCALAPPDATA%\Programs\Kami
; Veri (%LOCALAPPDATA%\Kami\data) kurulum/guncelleme ile SILINMEZ; kaldirirken sorulur (varsayilan: koru).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef DistDir
  #define DistDir "..\build_out\dist\Kami"
#endif
#ifndef OutDir
  #define OutDir "..\build_out"
#endif

[Setup]
AppId={{F27ACB8F-5660-4574-B6FA-305CA6828311}
AppName=Kami
AppVersion={#AppVersion}
AppVerName=Kami {#AppVersion}
AppPublisher=Metehan
AppPublisherURL=https://github.com/murasakimono/kami
DefaultDirName={localappdata}\Programs\Kami
DefaultGroupName=Kami
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutDir}
OutputBaseFilename=Kami-Setup-{#AppVersion}
SetupIconFile=kami.ico
UninstallDisplayIcon={app}\Kami.exe
UninstallDisplayName=Kami (KDM)
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
InfoAfterFile=brave_adimlari.txt
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Kami Download Manager kurulumu

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; eski surumden kalan derlenmis Python onbellegi / kaldirilmis eklentiler
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\plugins\*\__pycache__"

[Icons]
Name: "{group}\Kami"; Filename: "{app}\Kami.exe"; Comment: "Kami Download Manager"
Name: "{group}\Kami eklenti klasoru (Brave)"; Filename: "{app}\extension"
Name: "{group}\{cm:UninstallProgram,Kami}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Kami"; Filename: "{app}\Kami.exe"; Tasks: desktopicon

[Run]
; tarayici native host (Brave/Chrome/Edge) + magnet: isleyicisi kaydi
Filename: "{app}\Kami.exe"; Parameters: "--setup register"; StatusMsg: "Tarayici baglantisi kaydediliyor..."; Flags: runhidden waituntilterminated
Filename: "{app}\extension"; Description: "Brave eklenti klasorunu ac"; Flags: postinstall shellexec skipifsilent unchecked
Filename: "{code:BravePath}"; Parameters: "brave://extensions"; Description: "Brave eklentiler sayfasini ac"; Flags: postinstall nowait skipifsilent unchecked; Check: HasBrave
Filename: "{app}\Kami.exe"; Description: "{cm:LaunchProgram,Kami}"; Flags: postinstall nowait skipifsilent
; sessiz guncellemede Kami kendiliginden yeniden acilsin
Filename: "{app}\Kami.exe"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{app}\Kami.exe"; Parameters: "--setup unregister"; RunOnceId: "KamiUnregister"; Flags: runhidden waituntilterminated

[UninstallDelete]
Type: filesandordirs; Name: "{app}\plugins"
Type: filesandordirs; Name: "{app}\_internal"

[Code]
function BravePath(Param: String): String;
begin
  Result := ExpandConstant('{commonpf}\BraveSoftware\Brave-Browser\Application\brave.exe');
  if not FileExists(Result) then
    Result := ExpandConstant('{localappdata}\BraveSoftware\Brave-Browser\Application\brave.exe');
end;

function HasBrave: Boolean;
begin
  Result := FileExists(BravePath(''));
end;

procedure QuitKami(Dir: String);
var
  RC: Integer;
begin
  { calisan Kami'yi duzgun kapat (aria2 + dosyalar serbest kalsin); en fazla ~10 sn bekler }
  if FileExists(Dir + '\Kami.exe') then
    Exec(Dir + '\Kami.exe', '--quit', Dir, SW_HIDE, ewWaitUntilTerminated, RC);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  QuitKami(ExpandConstant('{app}'));
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  QuitKami(ExpandConstant('{app}'));
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DelTree(ExpandConstant('{app}'), True, True, True);   { kilitli kalan bos klasorler (bin vb.) }
    DataDir := ExpandConstant('{localappdata}\Kami');
    if DirExists(DataDir) and (not UninstallSilent) then
      if MsgBox('Kami ayarlari, gecmisi ve indirilen Whisper/UVR araclari da silinsin mi?' + #13#10 +
                '(' + DataDir + ')' + #13#10#13#10 + 'Hayir = korunur (yeniden kurunca kaldigin yerden devam eder).',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
