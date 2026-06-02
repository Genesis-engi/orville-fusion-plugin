[CmdletBinding()]
param(
  [string]$IsccPath = "",
  [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptRoot "..")).Path
$ManifestPath = Join-Path $RepoRoot "OrvilleFusionAddIn\OrvilleFusionAddIn.manifest"
$InstallerScript = Join-Path $RepoRoot "installer\OrvilleFusionPlugin.iss"
$DistDir = Join-Path $RepoRoot "dist"

function Resolve-InnoCompiler {
  param([string]$RequestedPath)

  if (-not [string]::IsNullOrWhiteSpace($RequestedPath)) {
    if (-not (Test-Path $RequestedPath)) {
      throw "Inno Setup compiler not found: $RequestedPath"
    }
    return (Resolve-Path $RequestedPath).Path
  }

  $Command = Get-Command iscc.exe -ErrorAction SilentlyContinue
  if ($null -ne $Command) {
    return $Command.Source
  }

  $Candidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
  )

  foreach ($Candidate in $Candidates) {
    if (Test-Path $Candidate) {
      return $Candidate
    }
  }

  throw "Inno Setup 6 compiler was not found. Install it with: winget install --id JRSoftware.InnoSetup --exact"
}

if (-not (Test-Path $ManifestPath)) {
  throw "Fusion add-in manifest not found: $ManifestPath"
}
if (-not (Test-Path $InstallerScript)) {
  throw "Inno Setup script not found: $InstallerScript"
}

$ManifestText = Get-Content -Raw -Path $ManifestPath
$VersionMatch = [regex]::Match($ManifestText, '"version"\s*:\s*"([^"]+)"')
if (-not $VersionMatch.Success) {
  throw "Manifest version was not found: $ManifestPath"
}
$Version = $VersionMatch.Groups[1].Value
if ([string]::IsNullOrWhiteSpace($Version)) {
  throw "Manifest version is empty: $ManifestPath"
}

if (-not $SkipTests) {
  $Python = Get-Command python -ErrorAction SilentlyContinue
  if ($null -eq $Python) {
    Write-Warning "Python was not found on PATH; skipping unit tests."
  } else {
    Push-Location $RepoRoot
    try {
      & $Python.Source -m unittest discover -s tests
      if ($LASTEXITCODE -ne 0) {
        throw "Unit tests failed with exit code $LASTEXITCODE"
      }
    } finally {
      Pop-Location
    }
  }
}

$Compiler = Resolve-InnoCompiler -RequestedPath $IsccPath
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

Write-Host "Building Orville Fusion Plugin installer"
Write-Host "Version: $Version"
Write-Host "Compiler: $Compiler"
Write-Host "Output: $DistDir"

& $Compiler `
  "/DSourceRoot=$RepoRoot" `
  "/DAppVersion=$Version" `
  $InstallerScript

if ($LASTEXITCODE -ne 0) {
  throw "Inno Setup failed with exit code $LASTEXITCODE"
}

$Output = Join-Path $DistDir "OrvilleFusionPluginSetup-$Version.exe"
if (-not (Test-Path $Output)) {
  throw "Expected installer was not created: $Output"
}

Write-Host ""
Write-Host "Installer created:"
Write-Host $Output
