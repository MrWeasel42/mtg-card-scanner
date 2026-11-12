; Windows installer for MTG Card Scanner (Inno Setup 6.3+).
; Built automatically by .github/workflows/app.yml; the app files come from ..\publish.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{8F3C2B1A-6D2E-4E8A-9C51-6B1F3E2A7D10}
AppName=MTG Card Scanner
AppVersion={#MyAppVersion}
AppPublisher=MrWeasel42
AppPublisherURL=https://github.com/MrWeasel42/mtg-card-scanner
DefaultDirName={localappdata}\Programs\MTG Card Scanner
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=MTGCardScanner_Setup_{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\MTGCardScanner.exe
UninstallDisplayName=MTG Card Scanner

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"

[Files]
Source: "..\publish\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Clear out files from older versions so nothing stale is left behind.
Type: filesandordirs; Name: "{app}\*"

[Icons]
Name: "{autoprograms}\MTG Card Scanner"; Filename: "{app}\MTGCardScanner.exe"
Name: "{autodesktop}\MTG Card Scanner"; Filename: "{app}\MTGCardScanner.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MTGCardScanner.exe"; Description: "Start MTG Card Scanner"; Flags: nowait postinstall skipifsilent
; In-app updates run the installer silently; reopen the app afterwards.
Filename: "{app}\MTGCardScanner.exe"; Flags: nowait skipifnotsilent
