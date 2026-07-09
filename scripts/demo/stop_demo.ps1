[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RuntimeDir = Join-Path $RepoRoot ".runtime"
$BackendPidFile = Join-Path $RuntimeDir "demo-backend.pid"
$FrontendPidFile = Join-Path $RuntimeDir "demo-frontend.pid"

function Write-Info {
    param([string]$Message)
    Write-Host "[stop-demo] $Message"
}

function Write-WarningLine {
    param([string]$Message)
    Write-Host "[stop-demo] WARNING: $Message" -ForegroundColor Yellow
}

function Get-ProcessCommandLine {
    param([int]$ProcessId)

    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        return $process.CommandLine
    }
    catch {
        try {
            $process = Get-WmiObject Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
            return $process.CommandLine
        }
        catch {
            return $null
        }
    }
}

function Get-ChildProcessIds {
    param([int]$ParentProcessId)

    $children = @()
    try {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ParentProcessId" -ErrorAction Stop)
    }
    catch {
        try {
            $children = @(Get-WmiObject Win32_Process -Filter "ParentProcessId=$ParentProcessId" -ErrorAction Stop)
        }
        catch {
            $children = @()
        }
    }

    $ids = @()
    foreach ($child in $children) {
        $childId = [int]$child.ProcessId
        $ids += $childId
        $ids += Get-ChildProcessIds -ParentProcessId $childId
    }
    return $ids
}

function Test-CommandLineMarkers {
    param(
        [int]$ProcessId,
        [string[]]$Markers
    )

    $commandLine = Get-ProcessCommandLine -ProcessId $ProcessId
    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }

    foreach ($marker in $Markers) {
        if ($commandLine -notlike "*$marker*") {
            return $false
        }
    }

    return $true
}

function Stop-RecordedProcess {
    param(
        [string]$Name,
        [string]$PidFile,
        [string[]]$Markers
    )

    if (-not (Test-Path $PidFile)) {
        Write-Info "No $Name PID file found at $PidFile."
        return
    }

    $rawPid = (Get-Content -Path $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $processId = 0
    if (-not [int]::TryParse($rawPid, [ref]$processId)) {
        Write-WarningLine "Invalid $Name PID file; removing $PidFile."
        Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $process) {
        Write-Info "$Name PID $processId is not running; removing stale PID file."
        Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    if (-not (Test-CommandLineMarkers -ProcessId $processId -Markers $Markers)) {
        Write-WarningLine "PID $processId does not match the expected $Name command. Leaving it running and removing the stale PID file."
        Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    $processIds = @(Get-ChildProcessIds -ParentProcessId $processId)
    [array]::Reverse($processIds)
    $processIds += $processId
    $uniqueProcessIds = @($processIds | Select-Object -Unique)

    foreach ($id in $uniqueProcessIds) {
        $target = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($target) {
            Write-Info "Stopping $Name-owned process $id."
            Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        }
    }

    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
    Write-Info "Removed $Name PID file."
}

Stop-RecordedProcess `
    -Name "backend" `
    -PidFile $BackendPidFile `
    -Markers @("enterprise_ai_tool_gateway.api.http.app:app", "--port 8000")

Stop-RecordedProcess `
    -Name "frontend" `
    -PidFile $FrontendPidFile `
    -Markers @("run dev", "--port 5173")

Write-Info "Stop script finished."
