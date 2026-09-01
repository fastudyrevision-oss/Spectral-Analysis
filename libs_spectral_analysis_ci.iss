; ============================================================================
; LIBS Spectral Analysis Software — Inno Setup CI Build Script
; ============================================================================
;
; This file is used by GitHub Actions (and any CI environment).
; DistDir and OutputDir are passed in via /D command-line defines:
;
;   iscc /DDistDir="..." /DOutputDir="..." libs_spectral_analysis_ci.iss
;
; If you need to build locally with this file:
;   iscc /DDistDir="%cd%\dist\LIBS_Analysis" /DOutputDir="%cd%\installer" libs_spectral_analysis_ci.iss
;
; The original "libs spectral analysis.iss" with hardcoded paths is kept
; for convenience when building manually on the dev machine.
; ============================================================================

#ifndef DistDir
  #error DistDir must be defined on the command line: /DDistDir="path\to\dist\LIBS_Analysis"
#endif
#ifndef OutputDir
  #define OutputDir "installer"
#endif

#define MyAppName      "LIBS Spectral Analysis"
#define MyAppVersion   "1.1.1"
#define MyAppPublisher "JFD Tech"
#define MyAppURL       "https://www.jfdtech.info"
#define MyAppExeName   "LIBS_Analysis.exe"
#define MyAppAssocName MyAppName + " File"
#define MyAppAssocExt  ".myp"
#define MyAppAssocKey  StringChange(MyAppAssocName, " ", "") + MyAppAssocExt

; ── [Setup] ──────────────────────────────────────────────────────────────────
[Setup]
AppId={{EB19045F-9136-4E3D-BFEE-D4394FF0896D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={autopf}\{#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
DisableProgramGroupPage=yes

OutputDir={#OutputDir}
OutputBaseFilename=LIBS_Spectral_Analysis_Setup_{#MyAppVersion}
SetupIconFile=assets\icon.ico
SolidCompression=yes
WizardStyle=modern

; ── [Languages] ──────────────────────────────────────────────────────────────
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── [Tasks] ──────────────────────────────────────────────────────────────────
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

; ── [Files] ──────────────────────────────────────────────────────────────────
[Files]

; Application binaries → Program Files
Source: "{#DistDir}\*"; \
  DestDir: "{app}"; \
  Excludes: "_internal\NIST database\*,_internal\NIST database,_internal\Processed Data\*,_internal\Processed Data"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; NIST database → ProgramData (writable, never overwritten on reinstall)
Source: "{#DistDir}\_internal\NIST database\Neutral lines\*"; \
  DestDir: "{commonappdata}\LIBS_Analysis\NIST database\Neutral lines"; \
  Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist

Source: "{#DistDir}\_internal\NIST database\Ionic lines\*"; \
  DestDir: "{commonappdata}\LIBS_Analysis\NIST database\Ionic lines"; \
  Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist

; Processed Data → ProgramData
Source: "{#DistDir}\_internal\Processed Data\*"; \
  DestDir: "{commonappdata}\LIBS_Analysis\Processed Data"; \
  Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist

; ── [Dirs] ───────────────────────────────────────────────────────────────────
[Dirs]
Name: "{commonappdata}\LIBS_Analysis";                                Permissions: users-full everyone-full
Name: "{commonappdata}\LIBS_Analysis\NIST database";                  Permissions: users-full everyone-full
Name: "{commonappdata}\LIBS_Analysis\NIST database\Neutral lines";    Permissions: users-full everyone-full
Name: "{commonappdata}\LIBS_Analysis\NIST database\Ionic lines";      Permissions: users-full everyone-full
Name: "{commonappdata}\LIBS_Analysis\Processed Data";                 Permissions: users-full everyone-full

; ── [Registry] ───────────────────────────────────────────────────────────────
[Registry]
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocExt}\OpenWithProgids"; \
  ValueType: string; ValueName: "{#MyAppAssocKey}"; ValueData: ""; \
  Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}"; \
  ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocName}"; \
  Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}\DefaultIcon"; \
  ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocKey}\shell\open\command"; \
  ValueType: string; ValueName: ""; \
  ValueData: """{app}\{#MyAppExeName}"" ""%1"""

Root: HKLM; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; \
  ValueType: string; ValueName: "DatabasePath"; \
  ValueData: "{commonappdata}\LIBS_Analysis\NIST database"; \
  Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; \
  ValueType: string; ValueName: "ProcessedDataPath"; \
  ValueData: "{commonappdata}\LIBS_Analysis\Processed Data"; \
  Flags: uninsdeletekey

; ── [Icons] ──────────────────────────────────────────────────────────────────
[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
  WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "jfdtech.libsspectralanalysis.1.1.1"
Name: "{autodesktop}\{#MyAppName}";  Filename: "{app}\{#MyAppExeName}"; \
  Tasks: desktopicon; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "jfdtech.libsspectralanalysis.1.1.1"

; ── [Run] ────────────────────────────────────────────────────────────────────
[Run]
Filename: "{app}\{#MyAppExeName}"; \
  Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent; \
  WorkingDir: "{app}"
