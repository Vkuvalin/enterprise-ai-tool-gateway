[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RuntimeDir = Join-Path $RepoRoot ".runtime"
$InstancesDir = Join-Path $RuntimeDir "instances"
$LegacyPidFiles = @(
    (Join-Path $RuntimeDir "demo-backend.pid"),
    (Join-Path $RuntimeDir "demo-frontend.pid")
)

. (Join-Path $PSScriptRoot "runner_common.ps1")

function Write-Info {
    param([string]$Message)
    Write-Host "[stop-demo] $Message"
}

function Write-WarningLine {
    param([string]$Message)
    Write-Host "[stop-demo] WARNING: $Message" -ForegroundColor Yellow
}

$legacyFound = @($LegacyPidFiles | Where-Object { Test-Path -LiteralPath $_ })
if ($legacyFound.Count -gt 0) {
    Write-WarningLine "Legacy shared PID files were found and intentionally ignored because they do not prove per-instance ownership."
}

if (-not (Test-Path -LiteralPath $InstancesDir)) {
    Write-Info "No per-instance runner metadata found."
    exit 0
}

$hadRefusal = $false
$instanceDirectories = @(Get-ChildItem -LiteralPath $InstancesDir -Directory -Force -ErrorAction Stop)
foreach ($instanceDirectoryItem in $instanceDirectories) {
    if (($instanceDirectoryItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        Write-WarningLine "Ignoring reparse-point instance directory: $($instanceDirectoryItem.FullName)"
        $hadRefusal = $true
        continue
    }

    $instanceId = $instanceDirectoryItem.Name
    if ($instanceId -notmatch '^[0-9a-f]{32}$') {
        Write-WarningLine "Ignoring unrecognized instance directory: $($instanceDirectoryItem.FullName)"
        $hadRefusal = $true
        continue
    }

    foreach ($service in @("frontend", "backend")) {
        $metadataPath = Join-Path $instanceDirectoryItem.FullName "$service.json"
        if (-not (Test-Path -LiteralPath $metadataPath)) {
            continue
        }

        $loaded = Read-DemoOwnershipRecord `
            -MetadataPath $metadataPath `
            -ExpectedInstanceId $instanceId `
            -ExpectedService $service `
            -RepoRoot $RepoRoot
        if (-not $loaded.IsValid) {
            Write-WarningLine "Refusing invalid $service metadata at ${metadataPath}: $($loaded.Error)"
            $hadRefusal = $true
            continue
        }

        $result = Stop-DemoOwnedProcess `
            -OwnershipRecord $loaded.Record `
            -RepoRoot $RepoRoot `
            -MessagePrefix "stop-demo"
        if ($result.CanRemoveMetadata) {
            if (-not (Remove-DemoOwnershipRecordIfMatching `
                -MetadataPath $metadataPath `
                -OwnershipRecord $loaded.Record `
                -RepoRoot $RepoRoot `
                -MessagePrefix "stop-demo")) {
                $hadRefusal = $true
            }
        }
        else {
            $hadRefusal = $true
        }
    }

    Remove-DemoInstanceMetadataIfEmpty `
        -InstanceDirectory $instanceDirectoryItem.FullName `
        -InstanceId $instanceId `
        -MessagePrefix "stop-demo"
}

if ($hadRefusal) {
    Write-WarningLine "Stop script finished with one or more unverifiable records left untouched."
    exit 1
}

Write-Info "Stop script finished; all verified runner-owned instances are stopped."
exit 0
