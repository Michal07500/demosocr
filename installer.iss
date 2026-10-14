; Inštalátor aplikácie Kompletačný list (Inno Setup 6).
; Zostavuje ho GitHub Actions z priečinka dist\KompletacnyList.

#define AppName "Kompletačný list"
#define AppExe "KompletacnyList.exe"
#define AppVersion GetEnv("APP_VERSION")
#if AppVersion == ""
  #define AppVersion "1.0"
#endif

[Setup]
AppId={{8F3C2A51-6B1E-4C2B-9C7A-4E2D1F0A9B11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
DefaultDirName={autopf}\KompletacnyList
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; inštalácia bez práv správcu (do priečinka používateľa)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer
OutputBaseFilename=KompletacnyList-Instalator
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
#if FileExists(AddBackslash(CompilerPath) + "Languages\Slovak.isl")
Name: "sk"; MessagesFile: "compiler:Languages\Slovak.isl"
#else
Name: "cs"; MessagesFile: "compiler:Languages\Czech.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "Vytvoriť ikonu na pracovnej ploche"; GroupDescription: "Ikony:"

[InstallDelete]
; pri aktualizácii zmaže staré súbory programu
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\KompletacnyList\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
; PDF -> pravé tlačidlo -> Odoslať na -> Kompletačný list
Name: "{usersendto}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Spustiť {#AppName}"; Flags: nowait postinstall skipifsilent
