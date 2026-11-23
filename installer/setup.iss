; The Cassette app's installer (Inno Setup 7). Built by tools\build_app.py, which passes:
;   AppName, AppVersion, SourceDir (the PyInstaller app folder), IconFile.
; Installs for the current user only (no admin prompt), into %LOCALAPPDATA%\Programs\Cassette.

#ifndef AppName
  #define AppName "Cassette"
#endif
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6C2B5F3A-9E41-4B8D-A7C2-3D5E8F1A2B46}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppName}.exe
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; the running app holds this mutex (cassette.single_instance): setup and uninstall close it first
AppMutex=Local\{#AppName}Companion
CloseApplications=yes

[Tasks]
Name: "autostart"; Description: "Start {#AppName} with Windows (recommended: it runs quietly in the tray)"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
; the licence and the bundled libraries' notices go with the program
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD-PARTY-NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppName}.exe"

[Registry]
; the same entry the app's own "Start with Windows" menu item uses
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppName}.exe"""; Tasks: autostart; Flags: uninsdeletevalue
; if it was turned on from the app's own menu instead: removed on uninstall too
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "{#AppName}"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
