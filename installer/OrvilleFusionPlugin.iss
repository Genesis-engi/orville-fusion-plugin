#ifndef SourceRoot
  #define SourceRoot ".."
#endif

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define AppName "Orville Fusion Plugin"
#define Publisher "Ballista Labs Inc."
#define PluginName "OrvilleFusionAddIn"
#define CurrentAddInDir "{userappdata}\Autodesk\Autodesk Fusion\API\AddIns\" + PluginName
#define LegacyAddInDir "{userappdata}\Autodesk\Autodesk Fusion 360\API\AddIns\" + PluginName

[Setup]
AppId={{2CF96DB8-3199-4A21-9A39-61E7DD10F3D0}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
AppPublisherURL=https://www.ballistalabs.ai
AppSupportURL=https://www.ballistalabs.ai
AppUpdatesURL=https://www.ballistalabs.ai
DefaultDirName={localappdata}\Programs\Orville Fusion Plugin
DefaultGroupName=Orville Fusion Plugin
DisableDirPage=yes
DisableProgramGroupPage=yes
OutputDir={#SourceRoot}\dist
OutputBaseFilename=OrvilleFusionPluginSetup-{#AppVersion}
SetupIconFile={#SourceRoot}\installer\orville.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}
UninstallDisplayIcon={uninstallexe}
InfoAfterFile={#SourceRoot}\installer\after-install.txt

[InstallDelete]
Type: filesandordirs; Name: "{#CurrentAddInDir}"
Type: filesandordirs; Name: "{#LegacyAddInDir}"

[Files]
Source: "{#SourceRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\OrvilleFusionAddIn\*"; DestDir: "{#CurrentAddInDir}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__,*.pyc,*.pyo,*.log,orville_job_state.json,.DS_Store,Thumbs.db"
Source: "{#SourceRoot}\OrvilleFusionAddIn\*"; DestDir: "{#LegacyAddInDir}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__,*.pyc,*.pyo,*.log,orville_job_state.json,.DS_Store,Thumbs.db"

[UninstallDelete]
Type: filesandordirs; Name: "{#CurrentAddInDir}"
Type: filesandordirs; Name: "{#LegacyAddInDir}"

[Code]
function InitializeSetup(): Boolean;
begin
  if CheckForMutexes('Fusion360Mutex') then begin
    MsgBox('Autodesk Fusion appears to be running. Install can continue, but restart Fusion after setup completes so it reloads the Orville add-in files.', mbInformation, MB_OK);
  end;
  Result := True;
end;
