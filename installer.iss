; Inno Setup script for MoreRobAccounts 2.0.0
; Requiere Inno Setup 6: https://jrsoftware.org/isinfo.php

#define AppName "MoreRobAccounts"
#define AppVersion "2.0.0"
#define AppPublisher "YondoPro189"
#define AppURL "https://github.com/YondoPro189/MoreRobAccounts"
#define AppExe "MoreRobAccountsUI.exe"

[Setup]
AppId={{A7B3C4D5-E6F7-4890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=LEEME.txt
OutputDir=release
OutputBaseFilename=MoreRobAccounts-Setup-{#AppVersion}-win64
SetupIconFile=assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
PrivilegesRequired=admin

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "accounts.template.json"; DestDir: "{app}"; DestName: "accounts.json"; Flags: onlyifdoesntexist ignoreversion
Source: "LEEME.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon; IconFilename: "{app}\assets\icon.ico"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Ejecutar {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\login_debug.log"
Type: files; Name: "{app}\_login_result.json"

[Code]
function InitializeSetup(): Boolean;
begin
  if not FileExists(ExpandConstant('{src}\dist\{#AppExe}')) then
  begin
    MsgBox('Compila primero el ejecutable:' + #13#10 + '  make_release.bat', mbError, MB_OK);
    Result := False;
  end
  else
    Result := True;
end;
