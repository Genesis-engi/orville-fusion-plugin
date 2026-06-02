# Orville Fusion Plugin

Open-source Autodesk Fusion add-in plan for using the Orville CAD API from inside Fusion.

## Goal

Build a Fusion add-in that gives users a small chat interface for:

- Creating Orville CAD jobs from prompts.
- Attaching reference images through a Fusion file picker.
- Polling job status and showing completion or failure state.
- Sending follow-up iterations against the same job.
- Downloading generated STEP artifacts.
- Importing the selected STEP artifact into the active Fusion design.

## Current Status

First implementation pass is in place:

- Fusion add-in manifest and Python entry point.
- HTML palette for API key entry, image selection, prompts, status, artifacts, download, and import actions.
- Standard-library Orville API client with JSON and multipart request support.
- Windows Credential Manager and macOS Keychain secure-storage wrapper.
- Non-secret local job state persistence.
- STEP import helper for Fusion's active design.
- Unit tests for non-Fusion modules.

Implementation plan:

- [docs/FUSION_IMPLEMENTATION_PLAN.md](docs/FUSION_IMPLEMENTATION_PLAN.md)

Fusion runtime behavior still needs manual verification inside Autodesk Fusion.

## Local Tests

```bash
python -m unittest discover -s tests
```

## Windows Installer

For end users, download the Windows setup executable from GitHub Releases:

```text
OrvilleFusionPluginSetup-0.1.0.exe
```

The installer registers with Windows Apps & Features and installs the Fusion add-in into Autodesk Fusion's per-user AddIns folders. After setup, restart Fusion and load `OrvilleFusionAddIn` from `Utilities > Add-Ins > Scripts and Add-Ins`.

The installer writes both current and legacy Fusion add-in roots because Fusion installations can still scan either path:

- Windows: `%appdata%\Autodesk\Autodesk Fusion\API\AddIns`
- Windows legacy: `%appdata%\Autodesk\Autodesk Fusion 360\API\AddIns`
- macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion/API/AddIns`

See [docs/INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md).

To build the Windows installer from source:

```powershell
scripts\build-windows-installer.ps1
```

That writes the local build artifact to `dist\OrvilleFusionPluginSetup-<version>.exe`.

The older `Install-OrvilleFusionPlugin.cmd` path is a development copy helper, not the release installer.

## Documentation Baseline

The plan is anchored to Autodesk's current Fusion API documentation and the Orville API contract verified on 2026-05-21. See the implementation plan for source URLs and decisions.

## License

The Orville Fusion plugin, including the installable Fusion add-in under `OrvilleFusionAddIn/`, is open source under the MIT License. See [LICENSE](LICENSE); the installed add-in folder also includes its own MIT license copy.
