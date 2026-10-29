; GameBooster telepítő (Inno Setup 6).
; Előtte: pyinstaller GameBooster.spec  →  dist\GameBooster\
; Fordítás: iscc /DAppVersion=3.0.0 installer\GameBooster.iss  →  dist\GameBooster-Setup-3.0.0.exe

#ifndef AppVersion
  #define AppVersion "3.0.0"
#endif

[Setup]
; Az AppId köti össze a verziókat: frissítéskor a régi telepítés helyére kerül
AppId={{8F3C2A51-6B7E-4D2C-9C1E-5A7B3D9E4F21}
AppName=GameBooster
AppVersion={#AppVersion}
AppPublisher=AdamDruszad
AppPublisherURL=https://github.com/AdamDruszad/pc-optimizer
AppSupportURL=https://github.com/AdamDruszad/pc-optimizer/issues
DefaultDirName={autopf}\GameBooster
DefaultGroupName=GameBooster
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
ChangesEnvironment=yes
UninstallDisplayIcon={app}\GameBooster.exe
UninstallDisplayName=GameBooster
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=GameBooster-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "hungarian"; MessagesFile: "compiler:Languages\Hungarian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "addtopath"; Description: "Hozzáadás a PATH-hoz (parancssorból: gamebooster)"; GroupDescription: "Egyéb:"

[Files]
Source: "..\dist\GameBooster\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\GameBooster"; Filename: "{app}\GameBooster.exe"; Comment: "Windows játékoptimalizáló, visszaállítható módosításokkal"
Name: "{autodesktop}\GameBooster"; Filename: "{app}\GameBooster.exe"; Tasks: desktopicon

[Registry]
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\GameBooster.exe"; Description: "{cm:LaunchProgram,GameBooster}"; Flags: nowait postinstall skipifsilent

[Code]
const
  EnvKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';

function NeedsAddPath(Dir: string): Boolean;
var
  Paths: string;
begin
  if not RegQueryStringValue(HKLM, EnvKey, 'Path', Paths) then
    Result := True
  else
    Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';') = 0;
end;

procedure RemoveFromPath(Dir: string);
var
  Paths: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKLM, EnvKey, 'Path', Paths) then
    exit;
  P := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';');
  if P = 0 then
    exit;
  { P a Paths-ben a mappa kezdete; az előtte (vagy az elején utána) álló ; is törlődik }
  if P > 1 then
    Delete(Paths, P - 1, Length(Dir) + 1)
  else
    Delete(Paths, 1, Length(Dir) + 1);
  RegWriteExpandStringValue(HKLM, EnvKey, 'Path', Paths);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFromPath(ExpandConstant('{app}'));
end;
