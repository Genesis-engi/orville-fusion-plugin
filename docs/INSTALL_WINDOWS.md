# Windows Install

## End-User Installer

Download the setup executable from GitHub Releases:

```text
OrvilleFusionPluginSetup-0.1.0.exe
```

The installer:

- installs the add-in into Autodesk Fusion's per-user AddIns folders;
- registers an uninstaller in Windows Apps & Features;
- avoids Python caches, logs, and local runtime files;
- includes the MIT license inside the installed `OrvilleFusionAddIn` folder;
- writes both current and legacy Fusion add-in roots because Fusion installations can still scan either path.

Installed add-in targets:

```text
%APPDATA%\Autodesk\Autodesk Fusion\API\AddIns\OrvilleFusionAddIn
%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\OrvilleFusionAddIn
```

After it finishes:

1. Restart Autodesk Fusion if it was already open.
2. Open `Utilities > Add-Ins > Scripts and Add-Ins`.
3. Click `All scripts and add-ins`.
4. Go to the `Add-Ins` tab.
5. Select `OrvilleFusionAddIn`.
6. Click `Run`.
7. Click the `Orville` command in the add-ins toolbar.

To uninstall, use Windows `Apps > Installed apps`, search for `Orville Fusion Plugin`, and uninstall it.

## Building The Installer

The release installer is built with Inno Setup 6:

```powershell
winget install --id JRSoftware.InnoSetup --exact
scripts\build-windows-installer.ps1
```

The build script reads the version from `OrvilleFusionAddIn\OrvilleFusionAddIn.manifest` and writes:

```text
dist\OrvilleFusionPluginSetup-<version>.exe
```

## Development Copy Helper

For local development only, the repository still includes a direct copy helper:

```powershell
C:\Users\ethen\Desktop\GENESIS\orville-fusion-plugin\Install-OrvilleFusionPlugin.cmd
```

That helper copies:

```text
C:\Users\ethen\Desktop\GENESIS\orville-fusion-plugin\OrvilleFusionAddIn
```

to the Fusion add-in roots. It is not intended for release distribution.
