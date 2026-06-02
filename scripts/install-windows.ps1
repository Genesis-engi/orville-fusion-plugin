[CmdletBinding(SupportsShouldProcess = $true)]
param(
  [string]$SourcePath = "",
  [string]$TargetRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$PluginName = "OrvilleFusionAddIn"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptRoot "..")).Path

if ([string]::IsNullOrWhiteSpace($SourcePath)) {
  $SourcePath = Join-Path $RepoRoot $PluginName
}

if ([string]::IsNullOrWhiteSpace($TargetRoot)) {
  if ([string]::IsNullOrWhiteSpace($env:APPDATA)) {
    throw "APPDATA is not set. Pass -TargetRoot explicitly."
  }
  $TargetRoots = @(
    (Join-Path $env:APPDATA "Autodesk\Autodesk Fusion\API\AddIns"),
    (Join-Path $env:APPDATA "Autodesk\Autodesk Fusion 360\API\AddIns")
  )
} else {
  $TargetRoots = @($TargetRoot)
}

$SourcePath = (Resolve-Path $SourcePath).Path
$SourceManifest = Join-Path $SourcePath "$PluginName.manifest"

if (-not (Test-Path $SourceManifest)) {
  throw "Fusion add-in manifest not found: $SourceManifest"
}

Write-Host "Installing Orville Fusion Plugin"
Write-Host "Source: $SourcePath"
Write-Host "Targets:"
foreach ($Root in $TargetRoots) {
  Write-Host "  $(Join-Path ([System.IO.Path]::GetFullPath($Root)) $PluginName)"
}
Write-Host ""

foreach ($Root in $TargetRoots) {
  $ResolvedTargetRoot = [System.IO.Path]::GetFullPath($Root)
  $TargetPath = Join-Path $ResolvedTargetRoot $PluginName
  $TargetManifest = Join-Path $TargetPath "$PluginName.manifest"

  if (-not $PSCmdlet.ShouldProcess($TargetPath, "Install Fusion add-in")) {
    continue
  }

  New-Item -ItemType Directory -Force -Path $ResolvedTargetRoot | Out-Null

  $robocopy = Get-Command robocopy.exe -ErrorAction SilentlyContinue
  if ($null -eq $robocopy) {
    if (Test-Path $TargetPath) {
      Remove-Item -Recurse -Force $TargetPath
    }
    Copy-Item -Recurse -Force $SourcePath $TargetPath
  } else {
    & robocopy.exe `
      $SourcePath `
      $TargetPath `
      /MIR `
      /XD __pycache__ .pytest_cache .ruff_cache .mypy_cache `
      /XF *.pyc *.pyo *.log .DS_Store Thumbs.db orville_job_state.json

    $robocopyExit = $LASTEXITCODE
    if ($robocopyExit -ge 8) {
      throw "robocopy failed with exit code $robocopyExit"
    }
  }

  Get-ChildItem -Path $TargetPath -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  Get-ChildItem -Path $TargetPath -Recurse -File -Include "*.pyc", "*.pyo" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

  if (-not (Test-Path $TargetManifest)) {
    throw "Install verification failed. Manifest missing from target: $TargetManifest"
  }

  Write-Host ""
  Write-Host "Installed successfully:"
  Write-Host "Manifest: $TargetManifest"
}

Write-Host ""
Write-Host "Next:"
Write-Host "1. Restart Autodesk Fusion if it was already open."
Write-Host "2. Open Utilities > Add-Ins > Scripts and Add-Ins."
Write-Host "3. Click All scripts and add-ins, then select the Add-Ins tab."
Write-Host "4. Select OrvilleFusionAddIn and click Run."
Write-Host "5. Click the Orville command in the add-ins toolbar."
