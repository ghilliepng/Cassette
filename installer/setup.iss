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
; an update the app started itself (updates.py: /VERYSILENT /RELAUNCH=1): start the new app
Filename: "{app}\{#AppName}.exe"; Flags: nowait; Check: Relaunching

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// Started by the app to update itself: it closed so it could be replaced, so start it again.
function Relaunching: Boolean;
begin
  Result := ExpandConstant('{param:relaunch|0}') = '1';
end;

// Uninstalling: offer to tidy up what the app made outside its own folder. Two questions, both
// optional, skipped in a silent uninstall:
//   - its settings and Spotify sign-in (%LOCALAPPDATA%\Cassette)
//   - the Cassette addon in World of Warcraft, at the folder the app recorded in its settings,
//     and only if that folder really is named Cassette

// The addon's folder from the app's settings (config.json, "addon_dir"), or '' if unknown.
function AddonDirFromConfig(ConfigFile: String): String;
var
  Raw: AnsiString;
  Text, Key: String;
  P: Integer;
begin
  Result := '';
  if not LoadStringFromFile(ConfigFile, Raw) then Exit;
  Text := String(Raw);
  Key := '"addon_dir": "';
  P := Pos(Key, Text);
  if P = 0 then Exit;
  Text := Copy(Text, P + Length(Key), MaxInt);
  P := Pos('"', Text);
  if P = 0 then Exit;
  Result := Copy(Text, 1, P - 1);
  StringChangeEx(Result, '\', '\', True);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir, AddonDir: String;
begin
  if (CurUninstallStep <> usPostUninstall) or UninstallSilent then Exit;
  DataDir := ExpandConstant('{localappdata}\{#AppName}');
  AddonDir := RemoveBackslash(AddonDirFromConfig(DataDir + '\config.json'));
  if DirExists(DataDir) and (MsgBox('Also remove your {#AppName} settings and Spotify sign-in from this PC?' + #13#10#13#10 +
      'Choose No to keep them, so a reinstall picks up where you left off.', mbConfirmation, MB_YESNO) = IDYES) then
    DelTree(DataDir, True, True, True);
  if (AddonDir <> '') and DirExists(AddonDir) and (CompareText(ExtractFileName(AddonDir), '{#AppName}') = 0) and
     (MsgBox('Also remove the {#AppName} addon from World of Warcraft?' + #13#10#13#10 + AddonDir, mbConfirmation, MB_YESNO) = IDYES) then
    DelTree(AddonDir, True, True, True);
end;
