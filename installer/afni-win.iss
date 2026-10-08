; Windows installer for an afni-win package (Inno Setup 6).
;
;   iscc /DAppVersion=26.2.09 /DNumericVersion=26.2.9.0 /DSourceDir=<package dir>
;        /DOutputDir=<dir> /DOutputName=<file name without .exe> installer\afni-win.iss
;
; Installs for the current user by default (no administrator rights); the
; wizard offers an installation for all users. Optionally adds the program
; directory to PATH and removes it again on uninstall. The default folder is
; C:\AFNI: the AFNI scripts do not support paths with spaces (D34), so the
; wizard refuses a folder whose path contains one.

#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef NumericVersion
  #error NumericVersion is required
#endif
#ifndef SourceDir
  #error SourceDir is required
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif
#ifndef OutputName
  #define OutputName "afni-win-setup"
#endif

#define AppName "AFNI for Windows"

[Setup]
AppId={{6F1D2B8E-4C3A-4E8B-9A57-2C1F0D6B7A41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=afni-win project
AppPublisherURL=https://github.com/notaskynet/afni-win
AppSupportURL=https://github.com/notaskynet/afni-win/issues
VersionInfoVersion={#NumericVersion}
DefaultDirName={sd}\AFNI
DefaultGroupName=AFNI
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
ChangesEnvironment=yes
LicenseFile=..\LICENSE
InfoAfterFile=getting-started.txt
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName} {#AppVersion}
ShowLanguageDialog=auto

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "addtopath"; Description: "Add AFNI to PATH (AFNI programs work in every Command Prompt and PowerShell window)"
Name: "desktopicon"; Description: "Create a desktop shortcut to the AFNI Shell"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "afni-shell.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "getting-started.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\AFNI Shell"; Filename: "{cmd}"; Parameters: "/c ""{app}\afni-tcsh.cmd"""; WorkingDir: "{sd}\"; Comment: "tcsh prompt with the AFNI programs and scripts"
Name: "{group}\AFNI Command Prompt"; Filename: "{cmd}"; Parameters: "/k ""{app}\afni-shell.cmd"""; WorkingDir: "{sd}\"; Comment: "Command prompt with the AFNI programs and scripts"
Name: "{group}\Getting started"; Filename: "{app}\getting-started.txt"
Name: "{group}\AFNI documentation"; Filename: "https://afni.nimh.nih.gov/"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\AFNI Shell"; Filename: "{cmd}"; Parameters: "/c ""{app}\afni-tcsh.cmd"""; WorkingDir: "{sd}\"; Tasks: desktopicon

[Run]
Filename: "{app}\getting-started.txt"; Description: "Open the getting-started notes"; Flags: postinstall shellexec skipifsilent nowait
Filename: "{cmd}"; Parameters: "/c ""{app}\afni-tcsh.cmd"""; WorkingDir: "{sd}\"; Description: "Open the AFNI Shell"; Flags: postinstall skipifsilent nowait unchecked

[Code]
const
  UserEnvironmentKey = 'Environment';
  SystemEnvironmentKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';

function EnvironmentRoot: Integer;
begin
  if IsAdminInstallMode then
    Result := HKEY_LOCAL_MACHINE
  else
    Result := HKEY_CURRENT_USER;
end;

function EnvironmentKey: String;
begin
  if IsAdminInstallMode then
    Result := SystemEnvironmentKey
  else
    Result := UserEnvironmentKey;
end;

{ Position of Dir as a whole entry of the ';'-separated Path, or 0. }
function PathEntryPos(Path, Dir: String): Integer;
begin
  Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Path) + ';');
end;

procedure AddToPath(Dir: String);
var
  Path: String;
begin
  if not RegQueryStringValue(EnvironmentRoot, EnvironmentKey, 'Path', Path) then
    Path := '';
  if PathEntryPos(Path, Dir) > 0 then
    exit;
  if (Path <> '') and (Copy(Path, Length(Path), 1) <> ';') then
    Path := Path + ';';
  RegWriteExpandStringValue(EnvironmentRoot, EnvironmentKey, 'Path', Path + Dir);
end;

procedure RemoveFromPath(Dir: String);
var
  Path: String;
  P: Integer;
begin
  if not RegQueryStringValue(EnvironmentRoot, EnvironmentKey, 'Path', Path) then
    exit;
  P := PathEntryPos(Path, Dir);
  if P = 0 then
    exit;
  Path := ';' + Path + ';';
  Delete(Path, P, Length(Dir) + 1);
  Path := Copy(Path, 2, Length(Path) - 2);
  RegWriteExpandStringValue(EnvironmentRoot, EnvironmentKey, 'Path', Path);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpSelectDir) and (Pos(' ', WizardDirValue) > 0) then
  begin
    MsgBox('AFNI does not support folders whose path contains a space.' + #13#10 +
           'Please choose a folder such as C:\AFNI.', mbError, MB_OK);
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('addtopath') then
    AddToPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFromPath(ExpandConstant('{app}'));
end;
