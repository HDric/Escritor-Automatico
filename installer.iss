#define MyAppName "Escritor Automático"
#define MyAppExeName "EscritorAutomatico.exe"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{A8F4C5E3-9A21-4D32-B9C4-7C1B7E18D018}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
UninstallDisplayName={#MyAppName}
UninstallDisplayVersion={#AppVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
DefaultDirName={localappdata}\Programs\EscritorAutomatico
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousGroup=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
CloseApplications=yes
CloseApplicationsFilter=EscritorAutomatico.exe
RestartApplications=no
SetupMutex=EscritorAutomaticoSetupMutex
SetupLogging=yes
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
OutputDir=dist-installer
OutputBaseFilename=EscritorAutomatico-Setup-v{#AppVersion}
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoDescription=Instalador de Escritor Automático

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
; POST_INSTALACION.txt ya está copiado al bundle por CREAR_INSTALADOR.bat.
; Se incluye desde el directorio empaquetado para evitar una entrada duplicada.
Source: "dist\EscritorAutomatico\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Escritor Automático"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Guía de instalación"; Filename: "{app}\POST_INSTALACION.txt"; WorkingDir: "{app}"
Name: "{autodesktop}\Escritor Automático"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Escritor Automático"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\error_inicio.txt"
