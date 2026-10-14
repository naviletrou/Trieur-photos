; Installateur Windows du Trieur de photos (Inno Setup 6)
#define AppVersion GetEnv("TRIEUR_VERSION")

[Setup]
AppId={{6C1C6F5E-3D2B-4E0B-9D5B-7A2F0B6C9E41}
AppName=Trieur de photos
AppVersion={#AppVersion}
AppPublisher=Trieur de photos
DefaultDirName={localappdata}\Programs\Trieur de photos
DefaultGroupName=Trieur de photos
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=TrieurPhotos-Installation
SetupIconFile=..\assets\icone.ico
UninstallDisplayIcon={app}\TrieurPhotos.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "..\dist\TrieurPhotos\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Trieur de photos"; Filename: "{app}\TrieurPhotos.exe"
Name: "{autodesktop}\Trieur de photos"; Filename: "{app}\TrieurPhotos.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TrieurPhotos.exe"; Description: "Lancer le Trieur de photos"; Flags: nowait postinstall skipifsilent
