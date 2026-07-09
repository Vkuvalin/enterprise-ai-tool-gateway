[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$BackendHost = "127.0.0.1"
$BackendPort = 8000
$FrontendHost = "127.0.0.1"
$FrontendPort = 5173
$BackendHealthUrl = "http://127.0.0.1:8000/api/v1/health"
$FrontendUrl = "http://127.0.0.1:5173/"
$DashboardUrl = "http://127.0.0.1:5173/dashboard"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

$RuntimeDir = Join-Path $RepoRoot ".runtime"
$LogDir = Join-Path $RuntimeDir "logs"
$BackendLog = Join-Path $LogDir "backend.log"
$FrontendLog = Join-Path $LogDir "frontend.log"
$BackendPidFile = Join-Path $RuntimeDir "demo-backend.pid"
$FrontendPidFile = Join-Path $RuntimeDir "demo-frontend.pid"
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
    if (Test-Path $fallback) {
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
        if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) {
            return $false
        }
        $body = $response.Content | ConvertFrom-Json
        return $body.status -eq "ok"
    }
    catch {
        return $false
    }
}

function Test-FrontendReachable {
    try {
        $response = Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
    }
    catch {
        return $false
    }
}

function Start-LoggedCommand {
    param(
        [string]$Name,
        [string]$Executable,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [string]$LogPath
    )

    if (Test-Path $LogPath) {
        Clear-Content -Path $LogPath
    }
    else {
        New-Item -ItemType File -Path $LogPath -Force | Out-Null
    }

    $commandLine = "$(Quote-CmdArgument $Executable) $(Join-CmdArguments $Arguments) 1>>$(Quote-CmdArgument $LogPath) 2>>&1"
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

function Wait-ForReady {
    param(
        [string]$Name,
        [scriptblock]$Probe,
        [int]$TimeoutSeconds,
        [System.Diagnostics.Process]$Process,
        [string]$LogPath
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Probe) {
            return
        }

        if ($Process -and $Process.HasExited) {
            throw "$Name exited before becoming reachable. See log: $LogPath"
        }

        Start-Sleep -Seconds 1
    }

    throw "$Name did not become reachable within $TimeoutSeconds seconds. See log: $LogPath"
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
        return
    }

    $rawPid = (Get-Content -Path $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $processId = 0
    if (-not [int]::TryParse($rawPid, [ref]$processId)) {
        Write-WarningLine "Ignoring invalid $Name PID file: $PidFile"
        Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $process) {
        Write-Info "$Name process $processId is not running."
        Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    if (-not (Test-CommandLineMarkers -ProcessId $processId -Markers $Markers)) {
        Write-WarningLine "PID $processId does not match the expected $Name command; leaving it running."
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
}

function Stop-StartedProcesses {
    if ($StartedProcesses.Count -eq 0) {
        Write-Info "No runner-owned processes were started by this window."
        return
    }

    foreach ($entry in @($StartedProcesses)) {
        Stop-RecordedProcess -Name $entry.Name -PidFile $entry.PidFile -Markers $entry.Markers
    }
}

try {
    Write-Info "Repository root: $RepoRoot"
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

    $uvPath = Resolve-ToolPath -Name "uv"
    $npmPath = Resolve-NpmPath

    foreach ($relativePath in @(
        "pyproject.toml",
        "frontend/package.json",
        "src/enterprise_ai_tool_gateway/api/http/app.py"
    )) {
        $path = Join-Path $RepoRoot $relativePath
        if (-not (Test-Path $path)) {
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
        Write-Info "Starting backend on $BackendHost`:$BackendPort."
        $backendProcess = Start-LoggedCommand `
            -Name "backend" `
            -Executable $uvPath `
            -Arguments @("run", "uvicorn", "enterprise_ai_tool_gateway.api.http.app:app", "--host", $BackendHost, "--port", "$BackendPort") `
            -WorkingDirectory $RepoRoot `
            -LogPath $BackendLog
        Set-Content -Path $BackendPidFile -Value $backendProcess.Id -Encoding ASCII
        $StartedProcesses += [pscustomobject]@{
            Name = "backend"
            PidFile = $BackendPidFile
            Markers = @("enterprise_ai_tool_gateway.api.http.app:app", "--port $BackendPort")
        }
        $backendStarted = $true
        Wait-ForReady -Name "Backend" -Probe { Test-BackendHealthy } -TimeoutSeconds 60 -Process $backendProcess -LogPath $BackendLog
    }

    if (Test-FrontendReachable) {
        Write-Info "Frontend is already reachable; reusing $FrontendUrl."
    }
    elseif (Test-TcpPort -HostName $FrontendHost -Port $FrontendPort) {
        throw "Port $FrontendPort is occupied, but $FrontendUrl is not reachable. Stop the conflicting process and run the demo again."
    }
    else {
        Write-Info "Starting frontend on $FrontendHost`:$FrontendPort."
        $frontendProcess = Start-LoggedCommand `
            -Name "frontend" `
            -Executable $npmPath `
            -Arguments @("run", "dev", "--", "--host", $FrontendHost, "--port", "$FrontendPort") `
            -WorkingDirectory (Join-Path $RepoRoot "frontend") `
            -LogPath $FrontendLog
        Set-Content -Path $FrontendPidFile -Value $frontendProcess.Id -Encoding ASCII
        $StartedProcesses += [pscustomobject]@{
            Name = "frontend"
            PidFile = $FrontendPidFile
            Markers = @("run dev", "--port $FrontendPort")
        }
        $frontendStarted = $true
        Wait-ForReady -Name "Frontend" -Probe { Test-FrontendReachable } -TimeoutSeconds 90 -Process $frontendProcess -LogPath $FrontendLog
    }

    Write-Info "Opening dashboard: $DashboardUrl"
    try {
        Start-Process $DashboardUrl
    }
    catch {
        Write-WarningLine "Could not open the browser automatically. Open $DashboardUrl manually."
    }

    Write-Host ""
    Write-Host "Dashboard URL : $DashboardUrl"
    Write-Host "API health URL: $BackendHealthUrl"
    Write-Host "Backend log   : $BackendLog"
    Write-Host "Frontend log  : $FrontendLog"
    Write-Host ""

    if ($backendStarted -or $frontendStarted) {
        Write-Host "Press Q to stop processes started by this runner and exit."
    }
    else {
        Write-Host "Press Q to exit. No existing service will be stopped."
    }

    while ($true) {
        $key = [Console]::ReadKey($true)
        if ($key.Key -eq [ConsoleKey]::Q) {
            break
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
        Stop-StartedProcesses
    }
    exit 1
}
