; ============================================================================
; LIBS Spectral Analysis Software — Inno Setup Installer Script
; ============================================================================
;
; Install layout
; --------------
;   {app}  =  C:\Program Files\LIBS Spectral Analysis\
;             └─ LIBS_Analysis.exe           (launcher)
;             └─ src\                        (frozen Python bytecode)
;             └─ _internal\                  (DLLs: scipy, matplotlib, PyQt6)
;
;   {commonappdata}\LIBS_Analysis\           = C:\ProgramData\LIBS_Analysis\
;             └─ NIST database\
;                  ├─ Neutral lines\         ← user can add CSV/XLSX here
;                  └─ Ionic lines\           ← user can add CSV/XLSX here
;
;   {userappdata}\LIBS_Analysis\             = %APPDATA%\LIBS_Analysis\
;             └─ .nist_cache.db              (auto-built SQLite cache)
;             └─ recent_files.json           (recent-files history)
;
; Why ProgramData for the database?
;   Program Files is read-only for non-admin users on modern Windows.
;   ProgramData is writable by all users, so anyone can drop a new element
;   CSV into the folder and the software picks it up on the next Refresh.
;
; Build: Open this file in Inno Setup Compiler and press Compile (F9).
; ============================================================================

#define MyAppName      "LIBS Spectral Analysis"
#define MyAppVersion   "1.1.1"
#define MyAppPublisher "JFD Tech"
#define MyAppURL       "https://www.jfdtech.info"
#define MyAppExeName   "LIBS_Analysis.exe"
#define MyAppAssocName MyAppName + " File"
#define MyAppAssocExt  ".myp"
#define MyAppAssocKey  StringChange(MyAppAssocName, " ", "") + MyAppAssocExt

; Source root — the PyInstaller dist folder
#define DistDir "C:\Users\User\Desktop\Spectral Analysis\SpectralAnalysisSoftware\dist\LIBS_Analysis"

; ── [Setup] ──────────────────────────────────────────────────────────────────
[Setup]
AppId={{EB19045F-9136-4E3D-BFEE-D4394FF0896D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installed to Program Files (read-only for non-admins — code only goes here)
DefaultDirName={autopf}\{#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

; Require admin so we can write to Program Files AND set ProgramData perms
PrivilegesRequired=admin

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
DisableProgramGroupPage=yes

OutputDir=C:\Users\User\Desktop
OutputBaseFilename=LIBS_Spectral_Analysis_Setup
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

; ── Application binaries → Program Files (read-only, protected) ──────────────
; Copy everything from the PyInstaller dist folder.
; The NIST database and Processed Data are inside _internal\ in PyInstaller 6.x builds —
; we exclude them here and install them separately to ProgramData below.
Source: "{#DistDir}\*"; \
  DestDir: "{app}"; \
  Excludes: "_internal\NIST database\*,_internal\NIST database,_internal\Processed Data\*,_internal\Processed Data"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; ── NIST database → ProgramData (writable by all users) ──────────────────────
; Source is the copy inside _internal\ that PyInstaller 6.x produced.
; onlyifdoesntexist means reinstall/upgrade never wipes user-added files.
Source: "{#DistDir}\_internal\NIST database\Neutral lines\*"; \
  DestDir: "{commonappdata}\LIBS_Analysis\NIST database\Neutral lines"; \
  Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist

Source: "{#DistDir}\_internal\NIST database\Ionic lines\*"; \
  DestDir: "{commonappdata}\LIBS_Analysis\NIST database\Ionic lines"; \
  Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist

; ── Processed Data (pure-element reference CSVs) → ProgramData ───────────────
; Same pattern as NIST database: user-writable, never overwritten on reinstall.
; The app resolves this path at runtime via _get_processed_data_folder().
Source: "{#DistDir}\_internal\Processed Data\*"; \
  DestDir: "{commonappdata}\LIBS_Analysis\Processed Data"; \
  Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist

; ── [Dirs] ───────────────────────────────────────────────────────────────────
[Dirs]

; Create the ProgramData root and grant full control to all users so they
; can add, modify, and delete element files without needing admin rights.
Name: "{commonappdata}\LIBS_Analysis"; \
  Permissions: users-full everyone-full

Name: "{commonappdata}\LIBS_Analysis\NIST database"; \
  Permissions: users-full everyone-full

Name: "{commonappdata}\LIBS_Analysis\NIST database\Neutral lines"; \
  Permissions: users-full everyone-full

Name: "{commonappdata}\LIBS_Analysis\NIST database\Ionic lines"; \
  Permissions: users-full everyone-full

; Processed Data folder — writable so users can add/remove pure-element CSVs
Name: "{commonappdata}\LIBS_Analysis\Processed Data"; \
  Permissions: users-full everyone-full

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

; Store the ProgramData database path in the registry so the app can find it
; even if PROGRAMDATA is overridden by group policy.
Root: HKLM; Subkey: "Software\{#MyAppPublisher}\{#MyAppName}"; \
  ValueType: string; ValueName: "DatabasePath"; \
  ValueData: "{commonappdata}\LIBS_Analysis\NIST database"; \
  Flags: uninsdeletekey

; Store the Processed Data path in the registry for the same reason.
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
; Launch after install (optional, user can uncheck)
Filename: "{app}\{#MyAppExeName}"; \
  Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent; \
  WorkingDir: "{app}"
