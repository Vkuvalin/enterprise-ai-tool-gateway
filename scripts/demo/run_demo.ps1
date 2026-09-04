[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$BackendHost = "127.0.0.1"
$BackendPort = 8000
$FrontendHost = "127.0.0.1"
$FrontendPort = 5173
$BackendHealthUrl = "http://127.0.0.1:8000/api/v1/health"
$FrontendUrl = "http://127.0.0.1:5173/"
$FrontendMarkerUrl = "http://127.0.0.1:5173/gateway-demo-marker.txt"
$FrontendProxyHealthUrl = "http://127.0.0.1:5173/api/v1/health"
$FrontendMarkerContent = "enterprise-ai-tool-gateway:frontend:v1"
$DashboardUrl = "http://127.0.0.1:5173/dashboard"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

. (Join-Path $PSScriptRoot "runner_common.ps1")

$RuntimeDir = Join-Path $RepoRoot ".runtime"
$InstancesDir = Join-Path $RuntimeDir "instances"
$InstanceId = [guid]::NewGuid().ToString("N")
$InstanceDir = Join-Path $InstancesDir $InstanceId
$LogDir = Join-Path $RuntimeDir "logs\$InstanceId"
$InstanceMetadataPath = Join-Path $InstanceDir "instance.json"
$StartedProcesses = @()

function Write-Info {
    param([string]$Message)
    Write-Host "[demo] $Message"
}

function Write-WarningLine {
    param([string]$Message)
    Write-Host "[demo] WARNING: $Message" -ForegroundColor Yellow
}

function Quote-CmdArgument {
    param([string]$Value)

    if ($Value -notmatch '[\s"&|<>^]') {
        return $Value
    }

    return '"' + ($Value -replace '"', '\"') + '"'
}

function Join-CmdArguments {
    param([string[]]$Values)

    $quoted = @()
    foreach ($value in $Values) {
        $quoted += Quote-CmdArgument $value
    }
    return ($quoted -join " ")
}

function Resolve-ToolPath {
    param([string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "Required tool '$Name' was not found. Install it or add it to PATH."
}

function Resolve-NpmPath {
    $npmCommand = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    if (-not $npmCommand) {
        $npmCommand = Get-Command "npm" -ErrorAction SilentlyContinue
    }
    if ($npmCommand) {
        return $npmCommand.Source
    }

    $fallback = "C:\Program Files\nodejs\npm.cmd"
    if (Test-Path -LiteralPath $fallback) {
        return $fallback
    }

    throw "Required tool 'npm' was not found in PATH or at '$fallback'."
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutMs = 1000
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Test-BackendHealthy {
    try {
        $response = Invoke-WebRequest -Uri $BackendHealthUrl -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -ne 200) {
            return $false
        }
        $body = $response.Content | ConvertFrom-Json
        return $body.status -eq "ok"
    }
    catch {
        return $false
    }
}

function Get-FrontendIdentityState {
    if (-not (Test-TcpPort -HostName $FrontendHost -Port $FrontendPort -TimeoutMs 500)) {
        return "Unreachable"
    }

    try {
        $markerResponse = Invoke-WebRequest `
            -Uri $FrontendMarkerUrl `
            -UseBasicParsing `
            -MaximumRedirection 0 `
            -TimeoutSec 2
        if ($markerResponse.StatusCode -ne 200) {
            return "WrongIdentity"
        }

        $markerBody = ([string]$markerResponse.Content).TrimEnd([char[]]@("`r", "`n"))
        if (-not [string]::Equals($markerBody, $FrontendMarkerContent, [System.StringComparison]::Ordinal)) {
            return "WrongIdentity"
        }
    }
    catch {
        return "WrongIdentity"
    }

    try {
        $healthResponse = Invoke-WebRequest `
            -Uri $FrontendProxyHealthUrl `
            -UseBasicParsing `
            -MaximumRedirection 0 `
            -TimeoutSec 2
        if ($healthResponse.StatusCode -ne 200) {
            return "ProxyUnhealthy"
        }
        $health = $healthResponse.Content | ConvertFrom-Json
        if ($health.status -ne "ok") {
            return "ProxyUnhealthy"
        }
    }
    catch {
        return "ProxyUnhealthy"
    }

    return "Ready"
}

function Start-LoggedCommand {
    param(
        [string]$Name,
        [string]$Executable,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [string]$LogPath
    )

    New-Item -ItemType File -Path $LogPath -Force | Out-Null

    $commandLine = (
        'set "GATEWAY_DEMO_INSTANCE={0}" && {1} {2} 1>>{3} 2>>&1' -f
        $InstanceId,
        (Quote-CmdArgument $Executable),
        (Join-CmdArguments $Arguments),
        (Quote-CmdArgument $LogPath)
    )
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = $env:ComSpec
    $processInfo.Arguments = "/d /s /c ""$commandLine"""
    $processInfo.WorkingDirectory = $WorkingDirectory
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $processInfo
    if (-not $process.Start()) {
        throw "Failed to start $Name."
    }
    return $process
}

function New-OwnedProcessRecord {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("backend", "frontend")][string]$Service,
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)][string]$LogPath
    )

    try {
        $startTicks = [long]$Process.StartTime.ToUniversalTime().Ticks
    }
    catch {
        throw "Could not capture start identity for $Service process $($Process.Id)."
    }

    return [pscustomobject][ordered]@{
        schema_version = 1
        instance_id = $InstanceId
        service = $Service
        process_id = [int]$Process.Id
        process_start_utc_ticks = [string]$startTicks
        repo_root = Get-DemoCanonicalPath -Path $RepoRoot
        log_path = Get-DemoCanonicalPath -Path $LogPath
        created_utc = [DateTime]::UtcNow.ToString("o")
    }
}

function Publish-OwnedProcessRecord {
    param([Parameter(Mandatory = $true)]$Record)

    $metadataPath = Join-Path $InstanceDir "$($Record.service).json"
    $script:StartedProcesses += [pscustomobject]@{
        Record = $Record
        MetadataPath = $metadataPath
    }
    Write-DemoJsonAtomically -Path $metadataPath -Value $Record
}

function Test-OwnedProcessActive {
    param([Parameter(Mandatory = $true)]$Entry)

    $record = $Entry.Record
    $state = Get-DemoProcessState `
        -ProcessId ([int]$record.process_id) `
        -ExpectedStartUtcTicks ([long]$record.process_start_utc_ticks)
    if ($state.State -ne "Match") {
        return $false
    }

    $command = Get-DemoProcessCommandLine -ProcessId ([int]$record.process_id)
    if (-not $command.Success) {
        return $false
    }
    $markers = @(
        Get-DemoExpectedCommandMarkers `
            -RepoRoot $RepoRoot `
            -InstanceId $InstanceId `
            -Service ([string]$record.service)
    )
    return Test-DemoCommandLineMarkers -CommandLine $command.Value -Markers $markers
}

function Wait-ForReady {
    param(
        [string]$Name,
        [scriptblock]$Probe,
        [int]$TimeoutSeconds,
        $OwnedEntry,
        [string]$LogPath
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($OwnedEntry -and -not (Test-OwnedProcessActive -Entry $OwnedEntry)) {
            throw "$Name exited or lost its runner identity before becoming ready. See log: $LogPath"
        }

        if (& $Probe) {
            if ($OwnedEntry -and -not (Test-OwnedProcessActive -Entry $OwnedEntry)) {
                throw "$Name readiness was satisfied by a different process. See log: $LogPath"
            }
            return
        }

        Start-Sleep -Seconds 1
    }

    throw "$Name did not become ready within $TimeoutSeconds seconds. See log: $LogPath"
}

function Stop-StartedProcesses {
    if ($StartedProcesses.Count -eq 0) {
        Write-Info "No runner-owned processes were started by this window."
        Remove-DemoInstanceMetadataIfEmpty `
            -InstanceDirectory $InstanceDir `
            -InstanceId $InstanceId `
            -MessagePrefix "demo"
        return
    }

    $entries = @($StartedProcesses)
    [array]::Reverse($entries)
    foreach ($entry in $entries) {
        $result = Stop-DemoOwnedProcess `
            -OwnershipRecord $entry.Record `
            -RepoRoot $RepoRoot `
            -MessagePrefix "demo"
        if ($result.CanRemoveMetadata) {
            [void](Remove-DemoOwnershipRecordIfMatching `
                -MetadataPath $entry.MetadataPath `
                -OwnershipRecord $entry.Record `
                -RepoRoot $RepoRoot `
                -MessagePrefix "demo")
        }
    }

    Remove-DemoInstanceMetadataIfEmpty `
        -InstanceDirectory $InstanceDir `
        -InstanceId $InstanceId `
        -MessagePrefix "demo"
}

try {
    Write-Info "Repository root: $RepoRoot"
    Write-Info "Runner instance: $InstanceId"
    New-Item -ItemType Directory -Path $InstancesDir -Force | Out-Null
    New-Item -ItemType Directory -Path $InstanceDir -ErrorAction Stop | Out-Null
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

    $instanceRecord = [pscustomobject][ordered]@{
        schema_version = 1
        instance_id = $InstanceId
        runner_process_id = [int]$PID
        repo_root = Get-DemoCanonicalPath -Path $RepoRoot
        created_utc = [DateTime]::UtcNow.ToString("o")
    }
    Write-DemoJsonAtomically -Path $InstanceMetadataPath -Value $instanceRecord

    $uvPath = Resolve-ToolPath -Name "uv"
    $npmPath = Resolve-NpmPath

    foreach ($relativePath in @(
        "pyproject.toml",
        "frontend/package.json",
        "frontend/public/gateway-demo-marker.txt",
        "src/enterprise_ai_tool_gateway/api/http/app.py"
    )) {
        $path = Join-Path $RepoRoot $relativePath
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Expected file is missing: $relativePath"
        }
    }

    $backendStarted = $false
    $frontendStarted = $false

    if (Test-BackendHealthy) {
        Write-Info "Backend is already healthy; reusing $BackendHealthUrl."
    }
    elseif (Test-TcpPort -HostName $BackendHost -Port $BackendPort) {
        throw "Port $BackendPort is occupied, but $BackendHealthUrl did not return status ok. Stop the conflicting process and run the demo again."
    }
    else {
        $backendLog = Get-DemoExpectedLogPath -RepoRoot $RepoRoot -InstanceId $InstanceId -Service "backend"
        Write-Info "Starting backend on $BackendHost`:$BackendPort."
        $backendProcess = Start-LoggedCommand `
            -Name "backend" `
            -Executable $uvPath `
            -Arguments @("run", "uvicorn", "enterprise_ai_tool_gateway.api.http.app:app", "--host", $BackendHost, "--port", "$BackendPort") `
            -WorkingDirectory $RepoRoot `
            -LogPath $backendLog
        $backendRecord = New-OwnedProcessRecord -Service "backend" -Process $backendProcess -LogPath $backendLog
        Publish-OwnedProcessRecord -Record $backendRecord
        $backendEntry = $StartedProcesses[$StartedProcesses.Count - 1]
        $backendStarted = $true
        Wait-ForReady `
            -Name "Backend" `
            -Probe { Test-BackendHealthy } `
            -TimeoutSeconds 60 `
            -OwnedEntry $backendEntry `
            -LogPath $backendLog
    }

    $frontendState = Get-FrontendIdentityState
    if ($frontendState -eq "Ready") {
        Write-Info "Verified Gateway frontend is already ready; reusing $FrontendUrl."
    }
    elseif (Test-TcpPort -HostName $FrontendHost -Port $FrontendPort) {
        if ($frontendState -eq "ProxyUnhealthy") {
            throw "Port $FrontendPort serves the Gateway marker, but its /api/v1 health proxy is not ready. Resolve the conflicting or incomplete frontend and run the demo again."
        }
        throw "Port $FrontendPort is occupied by a service that is not the Gateway frontend. Stop the conflicting process and run the demo again."
    }
    else {
        $vitePackagePath = Join-Path $RepoRoot "frontend\node_modules\vite\package.json"
        if (-not (Test-Path -LiteralPath $vitePackagePath)) {
            throw "Frontend dependencies are missing. Run 'cd frontend' and 'npm install' once, then run the demo again."
        }

        $frontendLog = Get-DemoExpectedLogPath -RepoRoot $RepoRoot -InstanceId $InstanceId -Service "frontend"
        Write-Info "Starting frontend on $FrontendHost`:$FrontendPort."
        $frontendProcess = Start-LoggedCommand `
            -Name "frontend" `
            -Executable $npmPath `
            -Arguments @("run", "dev", "--", "--host", $FrontendHost, "--port", "$FrontendPort", "--strictPort") `
            -WorkingDirectory (Join-Path $RepoRoot "frontend") `
            -LogPath $frontendLog
        $frontendRecord = New-OwnedProcessRecord -Service "frontend" -Process $frontendProcess -LogPath $frontendLog
        Publish-OwnedProcessRecord -Record $frontendRecord
        $frontendEntry = $StartedProcesses[$StartedProcesses.Count - 1]
        $frontendStarted = $true
        Wait-ForReady `
            -Name "Frontend" `
            -Probe { (Get-FrontendIdentityState) -eq "Ready" } `
            -TimeoutSeconds 90 `
            -OwnedEntry $frontendEntry `
            -LogPath $frontendLog
    }

    if ($NoBrowser) {
        Write-Info "Browser launch skipped by -NoBrowser."
    }
    else {
        Write-Info "Opening dashboard: $DashboardUrl"
        try {
            Start-Process $DashboardUrl
        }
        catch {
            Write-WarningLine "Could not open the browser automatically. Open $DashboardUrl manually."
        }
    }

    Write-Host ""
    Write-Host "Dashboard URL : $DashboardUrl"
    Write-Host "API health URL: $BackendHealthUrl"
    Write-Host "Instance ID   : $InstanceId"
    Write-Host "Instance data : $InstanceDir"
    Write-Host "Instance logs : $LogDir"
    Write-Host ""

    if ($backendStarted -or $frontendStarted) {
        $exitMessage = "stop processes started by this runner instance and exit"
    }
    else {
        $exitMessage = "exit; reused services will not be stopped"
    }

    if ($NoBrowser) {
        while ($true) {
            $answer = Read-Host "Enter Q to $exitMessage"
            if ([string]::Equals($answer.Trim(), "q", [System.StringComparison]::OrdinalIgnoreCase)) {
                break
            }
        }
    }
    else {
        Write-Host "Press Q to $exitMessage."
        while ($true) {
            $key = [Console]::ReadKey($true)
            if ($key.Key -eq [ConsoleKey]::Q) {
                break
            }
        }
    }

    Stop-StartedProcesses
    Write-Info "Demo runner exited."
    exit 0
}
catch {
    Write-Host ""
    Write-Host "Demo runner failed: $($_.Exception.Message)" -ForegroundColor Red
    if ($StartedProcesses.Count -gt 0) {
        Write-Info "Cleaning up processes started during this failed launch."
    }
    Stop-StartedProcesses
    exit 1
}
