; VideoCue Installer Script for Inno Setup
; Compile with Inno Setup 6.x: https://jrsoftware.org/isinfo.php

#define MyAppName "VideoCue"
#define MyAppVersion "0.4.1"
#define MyAppPublisher "VideoCue Contributors"
#define MyAppURL "https://github.com/jpwalters/VideoCue"
#define MyAppExeName "VideoCue.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
AppId={{A8E3F7B1-9C4D-4E2A-8F1B-3D5C6E7A8B9C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE
OutputDir=installer_output
OutputBaseFilename=VideoCue-{#MyAppVersion}-Setup
SetupIconFile=resources\icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\VideoCue\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\VideoCue\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nVideoCue is a professional PTZ camera controller with VISCA-over-IP support, NDI video streaming, and USB gamepad control.%n%nIt is recommended that you close all other applications before continuing.

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
  
  // Check for .NET requirement (if needed in future)
  // if not IsDotNetInstalled(net472, 0) then
  // begin
  //   MsgBox('.NET Framework 4.7.2 or later is required. Please install it first.', mbError, MB_OK);
  //   Result := False;
  // end;
end;
