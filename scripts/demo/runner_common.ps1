function Get-DemoCanonicalPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $trimCharacters = [char[]]@(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    return [System.IO.Path]::GetFullPath($Path).TrimEnd($trimCharacters)
}

function Test-DemoStringEqual {
    param(
        [AllowNull()][string]$Left,
        [AllowNull()][string]$Right
    )

    return [string]::Equals($Left, $Right, [System.StringComparison]::OrdinalIgnoreCase)
}

function Get-DemoExpectedLogPath {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$InstanceId,
        [Parameter(Mandatory = $true)][ValidateSet("backend", "frontend")][string]$Service
    )

    return Join-Path $RepoRoot ".runtime\logs\$InstanceId\$Service.log"
}

function Get-DemoExpectedCommandMarkers {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$InstanceId,
        [Parameter(Mandatory = $true)][ValidateSet("backend", "frontend")][string]$Service
    )

    $logPath = Get-DemoExpectedLogPath `
        -RepoRoot $RepoRoot `
        -InstanceId $InstanceId `
        -Service $Service

    if ($Service -eq "backend") {
        return @(
            "GATEWAY_DEMO_INSTANCE=$InstanceId",
            "enterprise_ai_tool_gateway.api.http.app:app",
            "--port 8000",
            $logPath
        )
    }

    return @(
        "GATEWAY_DEMO_INSTANCE=$InstanceId",
        "run dev",
        "--port 5173",
        "--strictPort",
        $logPath
    )
}

function Get-DemoProcessState {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][long]$ExpectedStartUtcTicks
    )

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return [pscustomobject]@{
            State = "Missing"
            Process = $null
            ActualStartUtcTicks = $null
        }
    }

    try {
        $actualTicks = [long]$process.StartTime.ToUniversalTime().Ticks
    }
    catch {
        return [pscustomobject]@{
            State = "Unavailable"
            Process = $process
            ActualStartUtcTicks = $null
        }
    }

    if ($actualTicks -ne $ExpectedStartUtcTicks) {
        return [pscustomobject]@{
            State = "Changed"
            Process = $process
            ActualStartUtcTicks = $actualTicks
        }
    }

    return [pscustomobject]@{
        State = "Match"
        Process = $process
        ActualStartUtcTicks = $actualTicks
    }
}

function Get-DemoProcessCommandLine {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        if ($process -and -not [string]::IsNullOrWhiteSpace([string]$process.CommandLine)) {
            return [pscustomobject]@{ Success = $true; Value = [string]$process.CommandLine }
        }
    }
    catch {
        # Windows PowerShell installations without usable CIM can still expose WMI.
    }

    try {
        $process = Get-WmiObject Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        if ($process -and -not [string]::IsNullOrWhiteSpace([string]$process.CommandLine)) {
            return [pscustomobject]@{ Success = $true; Value = [string]$process.CommandLine }
        }
    }
    catch {
        # Ownership must fail closed when neither process API can expose the command.
    }

    return [pscustomobject]@{ Success = $false; Value = $null }
}

function Test-DemoCommandLineMarkers {
    param(
        [Parameter(Mandatory = $true)][string]$CommandLine,
        [Parameter(Mandatory = $true)][string[]]$Markers
    )

    foreach ($marker in $Markers) {
        if ([string]::IsNullOrEmpty($marker)) {
            return $false
        }

        if ($CommandLine.IndexOf($marker, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
            return $false
        }
    }

    return $true
}

function Get-DemoProcessTable {
    try {
        $items = @(Get-CimInstance Win32_Process -ErrorAction Stop)
        return [pscustomobject]@{ Success = $true; Items = $items }
    }
    catch {
        # Fall through to WMI for Windows PowerShell compatibility.
    }

    try {
        $items = @(Get-WmiObject Win32_Process -ErrorAction Stop)
        return [pscustomobject]@{ Success = $true; Items = $items }
    }
    catch {
        return [pscustomobject]@{ Success = $false; Items = @() }
    }
}

function ConvertTo-DemoCreationUtcTicks {
    param([Parameter(Mandatory = $true)]$CreationDate)

    try {
        if ($CreationDate -is [DateTime]) {
            return [pscustomobject]@{
                Success = $true
                Ticks = [long]$CreationDate.ToUniversalTime().Ticks
            }
        }

        $converted = [System.Management.ManagementDateTimeConverter]::ToDateTime(
            [string]$CreationDate
        )
        return [pscustomobject]@{
            Success = $true
            Ticks = [long]$converted.ToUniversalTime().Ticks
        }
    }
    catch {
        return [pscustomobject]@{ Success = $false; Ticks = [long]0 }
    }
}

function Get-DemoProcessCreationUtcTicks {
    param([Parameter(Mandatory = $true)][int]$ProcessId)

    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        if ($process) {
            return ConvertTo-DemoCreationUtcTicks -CreationDate $process.CreationDate
        }
    }
    catch {
        # Fall through to WMI for Windows PowerShell compatibility.
    }

    try {
        $process = Get-WmiObject Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        if ($process) {
            return ConvertTo-DemoCreationUtcTicks -CreationDate $process.CreationDate
        }
    }
    catch {
        # Process inspection is unavailable or the process exited during the query.
    }

    return [pscustomobject]@{ Success = $false; Ticks = [long]0 }
}

function Test-DemoCreationTimeMatches {
    param(
        [Parameter(Mandatory = $true)][long]$Left,
        [Parameter(Mandatory = $true)][long]$Right
    )

    # Win32_Process exposes microsecond precision while Process.StartTime may carry
    # sub-microsecond FILETIME ticks. One millisecond keeps the sources comparable
    # without allowing an older process to satisfy temporal ancestry checks.
    $toleranceTicks = [long]10000
    return [Math]::Abs($Left - $Right) -le $toleranceTicks
}

function Get-DemoOwnedTreeSnapshot {
    param(
        [Parameter(Mandatory = $true)][int]$RootProcessId,
        [Parameter(Mandatory = $true)][long]$RootStartUtcTicks,
        [Parameter(Mandatory = $true)][string[]]$RootMarkers
    )

    $rootState = Get-DemoProcessState `
        -ProcessId $RootProcessId `
        -ExpectedStartUtcTicks $RootStartUtcTicks
    if ($rootState.State -ne "Match") {
        return [pscustomobject]@{
            Success = $false
            Reason = "RootIdentity$($rootState.State)"
            Descendants = @()
        }
    }

    $commandResult = Get-DemoProcessCommandLine -ProcessId $RootProcessId
    if (-not $commandResult.Success) {
        return [pscustomobject]@{
            Success = $false
            Reason = "RootCommandUnavailable"
            Descendants = @()
        }
    }
    if (-not (Test-DemoCommandLineMarkers -CommandLine $commandResult.Value -Markers $RootMarkers)) {
        return [pscustomobject]@{
            Success = $false
            Reason = "RootCommandMismatch"
            Descendants = @()
        }
    }

    $tableResult = Get-DemoProcessTable
    if (-not $tableResult.Success) {
        return [pscustomobject]@{
            Success = $false
            Reason = "ProcessTableUnavailable"
            Descendants = @()
        }
    }

    $rootTableRecord = @(
        $tableResult.Items | Where-Object { [int]$_.ProcessId -eq $RootProcessId }
    ) | Select-Object -First 1
    if (-not $rootTableRecord) {
        return [pscustomobject]@{
            Success = $false
            Reason = "RootMissingFromProcessTable"
            Descendants = @()
        }
    }

    $rootCreation = ConvertTo-DemoCreationUtcTicks -CreationDate $rootTableRecord.CreationDate
    if (
        -not $rootCreation.Success -or
        -not (Test-DemoCreationTimeMatches -Left $rootCreation.Ticks -Right $RootStartUtcTicks)
    ) {
        return [pscustomobject]@{
            Success = $false
            Reason = "RootProcessTableIdentityMismatch"
            Descendants = @()
        }
    }

    $freshRootCreation = Get-DemoProcessCreationUtcTicks -ProcessId $RootProcessId
    if (
        -not $freshRootCreation.Success -or
        -not (Test-DemoCreationTimeMatches -Left $freshRootCreation.Ticks -Right $rootCreation.Ticks)
    ) {
        return [pscustomobject]@{
            Success = $false
            Reason = "RootProcessTableChanged"
            Descendants = @()
        }
    }

    $queue = New-Object System.Collections.Queue
    $queue.Enqueue([pscustomobject]@{
        ProcessId = $RootProcessId
        CreationUtcTicks = [long]$rootCreation.Ticks
        Depth = 0
    })
    $visited = @{}
    $visited[[string]$RootProcessId] = $true
    $descendants = New-Object System.Collections.ArrayList

    while ($queue.Count -gt 0) {
        $parent = $queue.Dequeue()
        foreach ($candidate in $tableResult.Items) {
            if ([int]$candidate.ParentProcessId -ne [int]$parent.ProcessId) {
                continue
            }

            $childId = [int]$candidate.ProcessId
            if ($visited.ContainsKey([string]$childId)) {
                continue
            }
            $visited[[string]$childId] = $true

            $candidateCreation = ConvertTo-DemoCreationUtcTicks -CreationDate $candidate.CreationDate
            if (-not $candidateCreation.Success) {
                return [pscustomobject]@{
                    Success = $false
                    Reason = "ChildCreationIdentityUnavailable"
                    Descendants = @()
                }
            }

            if ([long]$candidateCreation.Ticks -lt [long]$parent.CreationUtcTicks) {
                # ParentProcessId can point at a reused PID. A process older than
                # its alleged parent is not part of the owned process tree.
                continue
            }

            $depth = [int]$parent.Depth + 1
            $historicalChild = [pscustomobject]@{
                ProcessId = $childId
                CreationUtcTicks = [long]$candidateCreation.Ticks
                Depth = $depth
            }
            $queue.Enqueue($historicalChild)

            $child = Get-Process -Id $childId -ErrorAction SilentlyContinue
            if (-not $child) {
                continue
            }

            try {
                $childStartTicks = [long]$child.StartTime.ToUniversalTime().Ticks
            }
            catch {
                return [pscustomobject]@{
                    Success = $false
                    Reason = "ChildIdentityUnavailable"
                    Descendants = @()
                }
            }

            $freshChildCreation = Get-DemoProcessCreationUtcTicks -ProcessId $childId
            if (-not $freshChildCreation.Success) {
                $childAfterCreationQuery = Get-Process -Id $childId -ErrorAction SilentlyContinue
                if ($childAfterCreationQuery) {
                    return [pscustomobject]@{
                        Success = $false
                        Reason = "ChildCreationRevalidationUnavailable"
                        Descendants = @()
                    }
                }
                continue
            }

            if (
                -not (Test-DemoCreationTimeMatches `
                    -Left $freshChildCreation.Ticks `
                    -Right $candidateCreation.Ticks) -or
                -not (Test-DemoCreationTimeMatches `
                    -Left $childStartTicks `
                    -Right $freshChildCreation.Ticks)
            ) {
                # The snapshot PID was reused before live identity capture.
                continue
            }

            [void]$descendants.Add([pscustomobject]@{
                ProcessId = $childId
                StartUtcTicks = $childStartTicks
                CreationUtcTicks = [long]$candidateCreation.Ticks
                Depth = $depth
            })
        }
    }

    $rootState = Get-DemoProcessState `
        -ProcessId $RootProcessId `
        -ExpectedStartUtcTicks $RootStartUtcTicks
    if ($rootState.State -ne "Match") {
        return [pscustomobject]@{
            Success = $false
            Reason = "RootIdentity$($rootState.State)"
            Descendants = @()
        }
    }

    $commandResult = Get-DemoProcessCommandLine -ProcessId $RootProcessId
    if (
        -not $commandResult.Success -or
        -not (Test-DemoCommandLineMarkers -CommandLine $commandResult.Value -Markers $RootMarkers)
    ) {
        return [pscustomobject]@{
            Success = $false
            Reason = "RootCommandChanged"
            Descendants = @()
        }
    }

    return [pscustomobject]@{
        Success = $true
        Reason = $null
        Descendants = @($descendants)
    }
}

function Test-DemoOwnershipRecord {
    param(
        [Parameter(Mandatory = $true)]$Record,
        [Parameter(Mandatory = $true)][string]$ExpectedInstanceId,
        [Parameter(Mandatory = $true)][ValidateSet("backend", "frontend")][string]$ExpectedService,
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )

    try {
        $processId = 0
        $startTicks = [long]0
        if (
            [int]$Record.schema_version -ne 1 -or
            -not [string]::Equals([string]$Record.instance_id, $ExpectedInstanceId, [System.StringComparison]::Ordinal) -or
            -not [string]::Equals([string]$Record.service, $ExpectedService, [System.StringComparison]::Ordinal) -or
            -not [int]::TryParse([string]$Record.process_id, [ref]$processId) -or
            $processId -le 0 -or
            -not [long]::TryParse([string]$Record.process_start_utc_ticks, [ref]$startTicks) -or
            $startTicks -le 0
        ) {
            return [pscustomobject]@{ IsValid = $false; Error = "invalid fields"; Record = $null }
        }

        $expectedRoot = Get-DemoCanonicalPath -Path $RepoRoot
        $recordRoot = Get-DemoCanonicalPath -Path ([string]$Record.repo_root)
        if (-not (Test-DemoStringEqual -Left $recordRoot -Right $expectedRoot)) {
            return [pscustomobject]@{ IsValid = $false; Error = "repository root mismatch"; Record = $null }
        }

        $expectedLogPath = Get-DemoCanonicalPath -Path (
            Get-DemoExpectedLogPath `
                -RepoRoot $expectedRoot `
                -InstanceId $ExpectedInstanceId `
                -Service $ExpectedService
        )
        $recordLogPath = Get-DemoCanonicalPath -Path ([string]$Record.log_path)
        if (-not (Test-DemoStringEqual -Left $recordLogPath -Right $expectedLogPath)) {
            return [pscustomobject]@{ IsValid = $false; Error = "log path mismatch"; Record = $null }
        }

        return [pscustomobject]@{
            IsValid = $true
            Error = $null
            Record = [pscustomobject]@{
                schema_version = 1
                instance_id = $ExpectedInstanceId
                service = $ExpectedService
                process_id = $processId
                process_start_utc_ticks = $startTicks
                repo_root = $expectedRoot
                log_path = $expectedLogPath
                created_utc = [string]$Record.created_utc
            }
        }
    }
    catch {
        return [pscustomobject]@{ IsValid = $false; Error = $_.Exception.Message; Record = $null }
    }
}

function Read-DemoOwnershipRecord {
    param(
        [Parameter(Mandatory = $true)][string]$MetadataPath,
        [Parameter(Mandatory = $true)][string]$ExpectedInstanceId,
        [Parameter(Mandatory = $true)][ValidateSet("backend", "frontend")][string]$ExpectedService,
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )

    try {
        $raw = Get-Content -LiteralPath $MetadataPath -Raw -ErrorAction Stop
        $record = $raw | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        return [pscustomobject]@{
            IsValid = $false
            Error = "could not read valid JSON: $($_.Exception.Message)"
            Record = $null
        }
    }

    return Test-DemoOwnershipRecord `
        -Record $record `
        -ExpectedInstanceId $ExpectedInstanceId `
        -ExpectedService $ExpectedService `
        -RepoRoot $RepoRoot
}

function Write-DemoJsonAtomically {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value
    )

    if (Test-Path -LiteralPath $Path) {
        throw "Refusing to overwrite existing runner metadata: $Path"
    }

    $temporaryPath = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
    try {
        $json = $Value | ConvertTo-Json -Depth 6
        $encoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
        [System.IO.File]::WriteAllText($temporaryPath, $json + [Environment]::NewLine, $encoding)
        Move-Item -LiteralPath $temporaryPath -Destination $Path -ErrorAction Stop
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
        }
    }
}

function Stop-DemoOwnedProcess {
    param(
        [Parameter(Mandatory = $true)]$OwnershipRecord,
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [string]$MessagePrefix = "demo"
    )

    $instanceId = [string]$OwnershipRecord.instance_id
    $service = [string]$OwnershipRecord.service
    $validation = Test-DemoOwnershipRecord `
        -Record $OwnershipRecord `
        -ExpectedInstanceId $instanceId `
        -ExpectedService $service `
        -RepoRoot $RepoRoot
    if (-not $validation.IsValid) {
        Write-Host "[$MessagePrefix] WARNING: Refusing invalid $service ownership record: $($validation.Error)" -ForegroundColor Yellow
        return [pscustomobject]@{ Status = "InvalidRecord"; CanRemoveMetadata = $false }
    }

    $record = $validation.Record
    $processId = [int]$record.process_id
    $startTicks = [long]$record.process_start_utc_ticks
    $processState = Get-DemoProcessState -ProcessId $processId -ExpectedStartUtcTicks $startTicks

    if ($processState.State -eq "Missing") {
        Write-Host "[$MessagePrefix] $service process $processId is no longer running."
        return [pscustomobject]@{ Status = "AlreadyExited"; CanRemoveMetadata = $true }
    }
    if ($processState.State -eq "Changed") {
        Write-Host "[$MessagePrefix] $service PID $processId now belongs to a different process; leaving it running."
        return [pscustomobject]@{ Status = "IdentityChanged"; CanRemoveMetadata = $true }
    }
    if ($processState.State -ne "Match") {
        Write-Host "[$MessagePrefix] WARNING: Cannot verify $service PID $processId start identity; leaving it running." -ForegroundColor Yellow
        return [pscustomobject]@{ Status = "IdentityUnavailable"; CanRemoveMetadata = $false }
    }

    $markers = @(
        Get-DemoExpectedCommandMarkers `
            -RepoRoot $RepoRoot `
            -InstanceId $instanceId `
            -Service $service
    )
    $tree = Get-DemoOwnedTreeSnapshot `
        -RootProcessId $processId `
        -RootStartUtcTicks $startTicks `
        -RootMarkers $markers
    if (-not $tree.Success) {
        $rootAfterSnapshot = Get-DemoProcessState `
            -ProcessId $processId `
            -ExpectedStartUtcTicks $startTicks
        if ($rootAfterSnapshot.State -eq "Missing" -or $rootAfterSnapshot.State -eq "Changed") {
            Write-Host "[$MessagePrefix] $service process $processId exited while its tree was inspected."
            return [pscustomobject]@{ Status = "AlreadyExited"; CanRemoveMetadata = $true }
        }
        Write-Host "[$MessagePrefix] WARNING: Refusing to stop $service PID ${processId}: $($tree.Reason)." -ForegroundColor Yellow
        return [pscustomobject]@{ Status = $tree.Reason; CanRemoveMetadata = $false }
    }

    $stopFailed = $false
    $descendants = @($tree.Descendants | Sort-Object -Property Depth -Descending)
    foreach ($descendant in $descendants) {
        $childId = [int]$descendant.ProcessId
        $childState = Get-DemoProcessState `
            -ProcessId $childId `
            -ExpectedStartUtcTicks ([long]$descendant.StartUtcTicks)
        if ($childState.State -eq "Missing" -or $childState.State -eq "Changed") {
            continue
        }
        if ($childState.State -ne "Match") {
            Write-Host "[$MessagePrefix] WARNING: Cannot reverify descendant PID $childId; leaving the owned root running." -ForegroundColor Yellow
            $stopFailed = $true
            continue
        }

        $childStopFailed = $false
        try {
            Write-Host "[$MessagePrefix] Stopping $service-owned descendant process $childId."
            Stop-Process -Id $childId -Force -ErrorAction Stop
        }
        catch {
            $childAfterStop = Get-DemoProcessState `
                -ProcessId $childId `
                -ExpectedStartUtcTicks ([long]$descendant.StartUtcTicks)
            if ($childAfterStop.State -ne "Missing" -and $childAfterStop.State -ne "Changed") {
                Write-Host "[$MessagePrefix] WARNING: Could not stop descendant PID ${childId}: $($_.Exception.Message)" -ForegroundColor Yellow
                $childStopFailed = $true
            }
        }

        if (-not $childStopFailed) {
            $childStopped = $false
            for ($attempt = 0; $attempt -lt 30; $attempt++) {
                $childAfterStop = Get-DemoProcessState `
                    -ProcessId $childId `
                    -ExpectedStartUtcTicks ([long]$descendant.StartUtcTicks)
                if ($childAfterStop.State -eq "Missing" -or $childAfterStop.State -eq "Changed") {
                    $childStopped = $true
                    break
                }
                Start-Sleep -Milliseconds 100
            }
            if (-not $childStopped) {
                Write-Host "[$MessagePrefix] WARNING: Descendant PID $childId did not reach a verified stopped state." -ForegroundColor Yellow
                $childStopFailed = $true
            }
        }
        if ($childStopFailed) {
            $stopFailed = $true
        }
    }

    if ($stopFailed) {
        return [pscustomobject]@{ Status = "DescendantStopFailed"; CanRemoveMetadata = $false }
    }

    $rootState = Get-DemoProcessState -ProcessId $processId -ExpectedStartUtcTicks $startTicks
    if ($rootState.State -eq "Match") {
        $commandResult = Get-DemoProcessCommandLine -ProcessId $processId
        if (
            -not $commandResult.Success -or
            -not (Test-DemoCommandLineMarkers -CommandLine $commandResult.Value -Markers $markers)
        ) {
            $rootAfterCommandCheck = Get-DemoProcessState `
                -ProcessId $processId `
                -ExpectedStartUtcTicks $startTicks
            if ($rootAfterCommandCheck.State -eq "Missing" -or $rootAfterCommandCheck.State -eq "Changed") {
                Write-Host "[$MessagePrefix] $service root process $processId exited during final revalidation."
                return [pscustomobject]@{ Status = "Stopped"; CanRemoveMetadata = $true }
            }
            Write-Host "[$MessagePrefix] WARNING: Root identity changed before stop; leaving PID $processId running." -ForegroundColor Yellow
            return [pscustomobject]@{ Status = "RootRevalidationFailed"; CanRemoveMetadata = $false }
        }

        try {
            Write-Host "[$MessagePrefix] Stopping $service-owned root process $processId."
            Stop-Process -Id $processId -Force -ErrorAction Stop
        }
        catch {
            $rootAfterStop = Get-DemoProcessState `
                -ProcessId $processId `
                -ExpectedStartUtcTicks $startTicks
            if ($rootAfterStop.State -ne "Missing" -and $rootAfterStop.State -ne "Changed") {
                Write-Host "[$MessagePrefix] WARNING: Could not stop root PID ${processId}: $($_.Exception.Message)" -ForegroundColor Yellow
                return [pscustomobject]@{ Status = "RootStopFailed"; CanRemoveMetadata = $false }
            }
        }
    }
    elseif ($rootState.State -eq "Unavailable") {
        Write-Host "[$MessagePrefix] WARNING: Cannot reverify root PID $processId after child cleanup." -ForegroundColor Yellow
        return [pscustomobject]@{ Status = "RootRevalidationUnavailable"; CanRemoveMetadata = $false }
    }

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $rootState = Get-DemoProcessState -ProcessId $processId -ExpectedStartUtcTicks $startTicks
        if ($rootState.State -eq "Missing" -or $rootState.State -eq "Changed") {
            Write-Host "[$MessagePrefix] Stopped verified $service process tree for instance $instanceId."
            return [pscustomobject]@{ Status = "Stopped"; CanRemoveMetadata = $true }
        }
        Start-Sleep -Milliseconds 100
    }

    Write-Host "[$MessagePrefix] WARNING: $service root PID $processId is still running; retaining ownership metadata." -ForegroundColor Yellow
    return [pscustomobject]@{ Status = "StillRunning"; CanRemoveMetadata = $false }
}

function Remove-DemoOwnershipRecordIfMatching {
    param(
        [Parameter(Mandatory = $true)][string]$MetadataPath,
        [Parameter(Mandatory = $true)]$OwnershipRecord,
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [string]$MessagePrefix = "demo"
    )

    if (-not (Test-Path -LiteralPath $MetadataPath)) {
        return $true
    }

    $loaded = Read-DemoOwnershipRecord `
        -MetadataPath $MetadataPath `
        -ExpectedInstanceId ([string]$OwnershipRecord.instance_id) `
        -ExpectedService ([string]$OwnershipRecord.service) `
        -RepoRoot $RepoRoot
    if (-not $loaded.IsValid) {
        Write-Host "[$MessagePrefix] WARNING: Ownership metadata changed or is invalid; retaining $MetadataPath." -ForegroundColor Yellow
        return $false
    }

    if (
        [int]$loaded.Record.process_id -ne [int]$OwnershipRecord.process_id -or
        [long]$loaded.Record.process_start_utc_ticks -ne [long]$OwnershipRecord.process_start_utc_ticks
    ) {
        Write-Host "[$MessagePrefix] WARNING: Ownership metadata no longer matches the captured instance; retaining $MetadataPath." -ForegroundColor Yellow
        return $false
    }

    Remove-Item -LiteralPath $MetadataPath -Force -ErrorAction Stop
    return $true
}

function Remove-DemoInstanceMetadataIfEmpty {
    param(
        [Parameter(Mandatory = $true)][string]$InstanceDirectory,
        [Parameter(Mandatory = $true)][string]$InstanceId,
        [string]$MessagePrefix = "demo"
    )

    foreach ($service in @("backend", "frontend")) {
        if (Test-Path -LiteralPath (Join-Path $InstanceDirectory "$service.json")) {
            return
        }
    }

    $instancePath = Join-Path $InstanceDirectory "instance.json"
    if (Test-Path -LiteralPath $instancePath) {
        try {
            $instanceRecord = Get-Content -LiteralPath $instancePath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
            if (
                [int]$instanceRecord.schema_version -ne 1 -or
                -not [string]::Equals(
                    [string]$instanceRecord.instance_id,
                    $InstanceId,
                    [System.StringComparison]::Ordinal
                )
            ) {
                Write-Host "[$MessagePrefix] WARNING: Invalid instance metadata remains at $instancePath." -ForegroundColor Yellow
                return
            }
            Remove-Item -LiteralPath $instancePath -Force -ErrorAction Stop
        }
        catch {
            Write-Host "[$MessagePrefix] WARNING: Could not safely clean instance metadata at $instancePath." -ForegroundColor Yellow
            return
        }
    }

    $remaining = @(Get-ChildItem -LiteralPath $InstanceDirectory -Force -ErrorAction SilentlyContinue)
    if ($remaining.Count -eq 0) {
        Remove-Item -LiteralPath $InstanceDirectory -Force -ErrorAction SilentlyContinue
    }
}
