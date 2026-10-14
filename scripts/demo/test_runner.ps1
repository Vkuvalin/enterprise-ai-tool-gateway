[CmdletBinding()]
param(
    [ValidateSet("All", "CtrlC", "ForcedTermination", "StartupTermination", "Repeat", "Reuse", "OccupiedPort", "PartialStartupFailure")]
    [string]$Case = "All",
    [ValidateRange(1, 5)][int]$RepeatCount = 2,
    [ValidateRange(10, 180)][int]$StartupTimeoutSeconds = 120,
    [int]$SignalRunnerProcessId = 0
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$HarnessPath = $PSCommandPath
$HelperPath = Join-Path $PSScriptRoot "test_console_helper.cs"
if (-not ("Gateway.Demo.Tests.ConsoleProcess" -as [type])) {
    Add-Type -Path $HelperPath
}

# This path runs in a dedicated subprocess, never the invoking shell.
if ($SignalRunnerProcessId -gt 0) {
    try {
        [Gateway.Demo.Tests.ConsoleProcess]::SendCtrlC([uint32]$SignalRunnerProcessId)
        exit 0
    }
    catch {
        Write-Error $_
        exit 1
    }
}

$RuntimeDir = Join-Path $RepoRoot ".runtime"
$InstancesDir = Join-Path $RuntimeDir "instances"
$TestId = (Get-Date -Format "yyyyMMdd_HHmmss") + "_" + [guid]::NewGuid().ToString("N")
$OutputDir = Join-Path $RuntimeDir "test_runner\$TestId"
$PythonPathDir = Join-Path $OutputDir "python-path"
$ShimDir = Join-Path $OutputDir "frontend-failure-shim"
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$PowerShellExe = Join-Path $PSHOME "powershell.exe"
$RunnerPath = Join-Path $PSScriptRoot "run_demo.ps1"
$script:OwnedHandles = New-Object System.Collections.ArrayList
$script:Runners = New-Object System.Collections.ArrayList
$script:Results = New-Object System.Collections.ArrayList
$script:Sequence = 0
$Encoding = New-Object System.Text.UTF8Encoding($false)

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Wait-Condition {
    param([scriptblock]$Probe, [int]$Seconds, [string]$Failure)
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        if (& $Probe) { return }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    throw $Failure
}

function Test-Port {
    param([int]$Port)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $operation = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $operation.AsyncWaitHandle.WaitOne(200)) { return $false }
        $client.EndConnect($operation)
        return $true
    }
    catch { return $false }
    finally { $client.Dispose() }
}

function Assert-PortsFree {
    Assert-True (-not (Test-Port 8000)) "Port 8000 is occupied. This harness will not stop pre-existing or unidentified processes."
    Assert-True (-not (Test-Port 5173)) "Port 5173 is occupied. This harness will not stop pre-existing or unidentified processes."
}

function Test-DemoReady {
    try {
        $backend = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/health" -UseBasicParsing -TimeoutSec 2
        $proxy = Invoke-WebRequest -Uri "http://127.0.0.1:5173/api/v1/health" -UseBasicParsing -TimeoutSec 2
        $marker = Invoke-WebRequest -Uri "http://127.0.0.1:5173/gateway-demo-marker.txt" -UseBasicParsing -TimeoutSec 2
        return (($backend.Content | ConvertFrom-Json).status -eq "ok" -and ($proxy.Content | ConvertFrom-Json).status -eq "ok" -and ([string]$marker.Content).Trim() -eq "enterprise-ai-tool-gateway:frontend:v1")
    }
    catch { return $false }
}

function Register-Handle {
    param($Handle)
    [void]$script:OwnedHandles.Add($Handle)
    return $Handle
}

function Invoke-WithEnvironment {
    param([hashtable]$Variables, [scriptblock]$Action)
    $original = @{}
    foreach ($name in $Variables.Keys) {
        $original[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, [string]$Variables[$name], "Process")
    }
    try { return & $Action }
    finally {
        foreach ($name in $Variables.Keys) {
            [Environment]::SetEnvironmentVariable($name, $original[$name], "Process")
        }
    }
}

function Get-RunnerInstance {
    param($Runner)
    if ($Runner.InstanceId) { return $Runner.InstanceId }
    if (-not (Test-Path -LiteralPath $InstancesDir)) { return $null }
    foreach ($directory in @(Get-ChildItem -LiteralPath $InstancesDir -Directory)) {
        if ($Runner.BeforeInstances -contains $directory.Name) { continue }
        $metadata = Join-Path $directory.FullName "instance.json"
        if (-not (Test-Path -LiteralPath $metadata)) { continue }
        try {
            $record = Get-Content -LiteralPath $metadata -Raw | ConvertFrom-Json
            if ([uint32]$record.runner_process_id -eq $Runner.Native.ProcessId) {
                $Runner.InstanceId = $directory.Name
                return $Runner.InstanceId
            }
        }
        catch { }
    }
    return $null
}

function Start-Runner {
    param([string]$Label, [switch]$FrontendFailure)
    $script:Sequence++
    $before = @()
    if (Test-Path -LiteralPath $InstancesDir) {
        $before = @(Get-ChildItem -LiteralPath $InstancesDir -Directory | Select-Object -ExpandProperty Name)
    }
    $consoleLog = Join-Path $OutputDir ("{0:00}-{1}-console.log" -f $script:Sequence, $Label)
    $variables = @{
        UV_OFFLINE = "1"
        UV_NO_SYNC = "1"
        PYTHONDONTWRITEBYTECODE = "1"
        GATEWAY_RUNNER_TEST_DATABASE_URL = "sqlite+aiosqlite:///" + ((Join-Path $OutputDir "api.sqlite3") -replace "\\", "/")
        PYTHONPATH = $PythonPathDir
    }
    if ($env:PYTHONPATH) { $variables.PYTHONPATH += ";" + $env:PYTHONPATH }
    if ($FrontendFailure) { $variables.Path = $ShimDir + ";" + $env:Path }
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $RunnerPath + '" -NoBrowser'
    $native = Invoke-WithEnvironment $variables {
        [Gateway.Demo.Tests.ConsoleProcess]::Start($PowerShellExe, $arguments, $RepoRoot, $consoleLog, $true)
    }
    [void](Register-Handle $native)
    $runner = [pscustomobject]@{
        Label = $Label
        Native = $native
        ConsoleLog = $consoleLog
        BeforeInstances = $before
        InstanceId = $null
        ChildHandles = New-Object System.Collections.ArrayList
    }
    [void]$script:Runners.Add($runner)
    return $runner
}

function Capture-RunnerTree {
    param($Runner, [switch]$AllowExited, [switch]$AllowEmpty)
    # Only descendants of this retained process handle are eligible.
    if (-not $AllowExited) { Assert-True (-not $Runner.Native.HasExited) "Runner exited before its owned process tree could be captured." }
    $table = @(Get-CimInstance Win32_Process)
    $ownedIds = @{}
    $ownedTimes = @{}
    $ownedIds[[uint32]$Runner.Native.ProcessId] = $true
    $ownedTimes[[uint32]$Runner.Native.ProcessId] = $Runner.Native.CreatedUtc.Ticks
    $added = $true
    while ($added) {
        $added = $false
        foreach ($item in $table) {
            $childId = [uint32]$item.ProcessId
            if ($ownedIds.ContainsKey($childId) -or -not $ownedIds.ContainsKey([uint32]$item.ParentProcessId)) { continue }
            $snapshotCreatedUtc = ([DateTime]$item.CreationDate).ToUniversalTime()
            if ($snapshotCreatedUtc.Ticks -lt [long]$ownedTimes[[uint32]$item.ParentProcessId]) { continue }
            try {
                $handle = [Gateway.Demo.Tests.ConsoleProcess]::Open($childId)
                # CIM timestamps have microsecond precision; use the project's
                # existing 1ms tolerance when comparing to native FILETIME.
                if ([Math]::Abs($handle.CreatedUtc.Ticks - $snapshotCreatedUtc.Ticks) -gt 10000) {
                    $handle.Dispose()
                    continue
                }
                [void](Register-Handle $handle)
                [void]$Runner.ChildHandles.Add($handle)
                # Only a live, creation-verified handle may extend ancestry.
                # A disappeared/recycled snapshot parent cannot admit children.
                $ownedIds[$childId] = $true
                $ownedTimes[$childId] = $handle.CreatedUtc.Ticks
                $added = $true
            }
            catch {
                # A transient child can disappear during the snapshot.
                if (Get-Process -Id ([int]$childId) -ErrorAction SilentlyContinue) { throw }
            }
        }
    }
    if (-not $AllowEmpty) { Assert-True ($Runner.ChildHandles.Count -gt 0) "Ready demo unexpectedly had no observable descendants." }
}

function Wait-RunnerReady {
    param($Runner)
    Wait-Condition {
        if ($Runner.Native.HasExited) { throw "Runner $($Runner.Label) exited early. See $($Runner.ConsoleLog)" }
        [void](Get-RunnerInstance $Runner)
        Test-DemoReady
    } $StartupTimeoutSeconds "Demo did not become ready. See $($Runner.ConsoleLog)"
    Wait-Condition { -not [string]::IsNullOrEmpty([string](Get-RunnerInstance $Runner)) } 5 "Runner instance metadata was not captured."
    Capture-RunnerTree $Runner
}

function Send-RunnerCtrlC {
    param($Runner)
    Assert-True (-not $Runner.Native.HasExited) "Cannot send Ctrl+C to an exited test runner."
    $signalLog = Join-Path $OutputDir ($Runner.Label + "-signal.log")
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $HarnessPath + '" -SignalRunnerProcessId ' + $Runner.Native.ProcessId
    $helper = [Gateway.Demo.Tests.ConsoleProcess]::Start($PowerShellExe, $arguments, $RepoRoot, $signalLog, $false)
    [void](Register-Handle $helper)
    Assert-True ($helper.Wait(10000)) "Ctrl+C helper did not exit."
    Assert-True ($helper.ExitCode -eq 0) "Ctrl+C helper failed. See $signalLog"
}

function Assert-RunnerStopped {
    param($Runner, [switch]$ExpectGraceful)
    Assert-True ($Runner.Native.Wait(15000)) "Runner $($Runner.Label) did not terminate."
    Wait-Condition {
        $remaining = @($Runner.ChildHandles | Where-Object { -not $_.HasExited })
        $remaining.Count -eq 0 -and -not (Test-Port 8000) -and -not (Test-Port 5173)
    } 10 "Runner $($Runner.Label) left a captured descendant or a listening port."
    if ($ExpectGraceful) {
        Assert-True ($Runner.Native.ExitCode -eq 0) "Graceful runner exit returned $($Runner.Native.ExitCode)."
        $backendLog = Join-Path $RuntimeDir ("logs\" + $Runner.InstanceId + "\backend.log")
        Wait-Condition {
            (Test-Path -LiteralPath $backendLog) -and ((Get-Content -LiteralPath $backendLog -Raw) -match "Application shutdown complete")
        } 5 "Uvicorn graceful shutdown was not visible in $backendLog"
        $shutdownOutput = Get-Content -LiteralPath $Runner.ConsoleLog -Raw
        Assert-True ($shutdownOutput -notmatch "Some owned processes did not stop in time") "Normal Ctrl+C shutdown used the grace-timeout fallback."
        # The ASCII Y/N structure survives English, Russian, and mojibake output.
        # This invokes run_demo.ps1 directly; an outer user's batch shell is outside
        # this assertion and remains separately governed by run_demo.cmd.
        Assert-True ($shutdownOutput -notmatch "\[Y[^\r\n]*[/\\]N[^\r\n]*\]|Terminate batch job") "Normal Ctrl+C shutdown produced an inner batch-job confirmation prompt."
    }
}

function Test-CtrlC {
    param([string]$Label = "ctrl-c")
    Assert-PortsFree
    $runner = Start-Runner $Label
    Wait-RunnerReady $runner
    $console = Get-Content -LiteralPath $runner.ConsoleLog -Raw
    Assert-True ($console -match "Started server process|Uvicorn running") "Backend output was not pumped into the runner console log."
    Assert-True ($console -match "VITE|Local:") "Frontend output was not pumped into the runner console log."
    Send-RunnerCtrlC $runner
    Assert-RunnerStopped $runner -ExpectGraceful
}

function Test-ForcedTermination {
    Assert-PortsFree
    $runner = Start-Runner "forced-termination"
    Wait-RunnerReady $runner
    # Abrupt death of our exact retained process handle. This is NOT a simulated
    # click on the console's close button, or evidence of CTRL_CLOSE_EVENT delivery.
    $runner.Native.Terminate()
    Assert-RunnerStopped $runner
}

function Test-StartupTermination {
    for ($cycle = 1; $cycle -le 3; $cycle++) {
        Assert-PortsFree
        $runner = Start-Runner ("startup-termination-" + $cycle)
        Wait-Condition {
            if ($runner.Native.HasExited) { throw "Runner failed before the early termination trigger." }
            [void](Get-RunnerInstance $runner)
            (Get-Content -LiteralPath $runner.ConsoleLog -Raw) -match "Starting backend"
        } 20 "Early startup trigger was not observed."
        Assert-True (-not [string]::IsNullOrEmpty($runner.InstanceId)) "Early runner instance identity was not captured."
        # Kill immediately at the startup message, without waiting for health.
        $runner.Native.Terminate()
        Assert-True ($runner.Native.Wait(5000)) "Early test runner did not terminate."
        # Retaining the root kernel handle prevents identifying a different,
        # recycled root PID. Capture any surviving descendants only by ancestry.
        Capture-RunnerTree $runner -AllowExited -AllowEmpty
        $marker = "GATEWAY_DEMO_INSTANCE=" + $runner.InstanceId
        Wait-Condition {
            $liveCaptured = @($runner.ChildHandles | Where-Object { -not $_.HasExited })
            $markedWrappers = @(Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" | Where-Object {
                $_.CommandLine -and ([string]$_.CommandLine).IndexOf($marker, [StringComparison]::OrdinalIgnoreCase) -ge 0
            })
            $liveCaptured.Count -eq 0 -and $markedWrappers.Count -eq 0 -and -not (Test-Port 8000) -and -not (Test-Port 5173)
        } 10 "Early termination left a captured descendant, an instance-marked wrapper, or a listening port."
        # A listener could bind shortly after a failed launch-time ownership race.
        Start-Sleep -Milliseconds 500
        Assert-PortsFree
    }
}

function Test-Reuse {
    Assert-PortsFree
    $first = Start-Runner "reuse-first"
    Wait-RunnerReady $first
    $second = Start-Runner "reuse-second"
    Wait-Condition {
        if ($second.Native.HasExited) { throw "Second runner exited before reuse was observed." }
        [void](Get-RunnerInstance $second)
        (Get-Content -LiteralPath $second.ConsoleLog -Raw) -match "reusing"
    } $StartupTimeoutSeconds "Second runner did not report service reuse."
    Start-Sleep -Milliseconds 400
    $text = Get-Content -LiteralPath $second.ConsoleLog -Raw
    Assert-True ($text -match "Backend is already healthy" -and $text -match "frontend is already ready") "Both services must be explicitly reused."
    if ($second.InstanceId) {
        $instanceDir = Join-Path $InstancesDir $second.InstanceId
        Assert-True (-not (Test-Path -LiteralPath (Join-Path $instanceDir "backend.json"))) "Reusing runner claimed backend ownership."
        Assert-True (-not (Test-Path -LiteralPath (Join-Path $instanceDir "frontend.json"))) "Reusing runner claimed frontend ownership."
    }
    Send-RunnerCtrlC $second
    Assert-True ($second.Native.Wait(15000)) "Second runner did not exit."
    Assert-True ($second.Native.ExitCode -eq 0) "Second runner returned an unsuccessful exit."
    Assert-True (-not $first.Native.HasExited -and (Test-DemoReady)) "Stopping the reusing runner damaged the first runner's services."
    # Transient descendants may exit normally after startup; the stable service
    # roots and health must remain, rather than requiring every snapshot child live.
    foreach ($service in @("backend", "frontend")) {
        $recordPath = Join-Path $InstancesDir ($first.InstanceId + "\" + $service + ".json")
        $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
        $serviceHandle = @($first.ChildHandles | Where-Object { $_.ProcessId -eq [uint32]$record.process_id }) | Select-Object -First 1
        Assert-True ($null -ne $serviceHandle -and -not $serviceHandle.HasExited) "The first runner's $service root changed or exited during reuse."
    }
    Send-RunnerCtrlC $first
    Assert-RunnerStopped $first -ExpectGraceful
}

function Test-OccupiedPort {
    Assert-PortsFree
    $fixtureLog = Join-Path $OutputDir "occupied-port-listener.log"
    $arguments = '"' + (Join-Path $OutputDir "unrelated_listener.py") + '"'
    $fixture = [Gateway.Demo.Tests.ConsoleProcess]::Start($PythonExe, $arguments, $RepoRoot, $fixtureLog, $false)
    [void](Register-Handle $fixture)
    Wait-Condition { Test-Port 8000 } 5 "The test-owned unrelated listener did not bind port 8000."
    $runner = Start-Runner "occupied-port"
    Assert-True ($runner.Native.Wait(20000)) "Runner did not refuse the occupied port promptly."
    Assert-True ($runner.Native.ExitCode -ne 0) "Occupied, unhealthy port unexpectedly succeeded."
    $message = Get-Content -LiteralPath $runner.ConsoleLog -Raw
    Assert-True ($message -match "Port 8000 is occupied") "Expected occupied-port refusal was not visible."
    Assert-True (-not $fixture.HasExited -and (Test-Port 8000)) "Runner killed the unrelated test-owned listener."
    Assert-True (-not (Test-Port 5173)) "Runner launched frontend despite occupied backend port."
    $fixture.Terminate()
    Assert-True ($fixture.Wait(5000)) "Fixture listener did not stop."
    Wait-Condition { -not (Test-Port 8000) -and -not (Test-Port 5173) } 5 "Fixture socket cleanup did not complete."
    Assert-PortsFree
}

function Test-PartialStartupFailure {
    Assert-PortsFree
    $runner = Start-Runner "partial-startup-failure" -FrontendFailure
    Wait-Condition {
        [void](Get-RunnerInstance $runner)
        $runner.Native.HasExited
    } $StartupTimeoutSeconds "Intentional frontend startup failure did not terminate the runner."
    Assert-True ($runner.Native.ExitCode -ne 0) "Intentional frontend failure returned success."
    Assert-True (-not [string]::IsNullOrEmpty($runner.InstanceId)) "No test runner instance was captured."
    $backendLog = Join-Path $RuntimeDir ("logs\" + $runner.InstanceId + "\backend.log")
    Assert-True ((Test-Path -LiteralPath $backendLog) -and ((Get-Content -LiteralPath $backendLog -Raw) -match "Started server process")) "Partial startup test did not actually start the backend."
    Wait-Condition { -not (Test-Port 8000) -and -not (Test-Port 5173) } 10 "Startup failure leaked a listening service."
    Assert-True ((Get-Content -LiteralPath $runner.ConsoleLog -Raw) -match "intentional frontend fixture failure") "PATH shim was not the source of the frontend failure."
}

function Stop-HarnessOwnedProcesses {
    # Reverse launch/capture order. A retained handle cannot hit a recycled PID.
    for ($index = $script:OwnedHandles.Count - 1; $index -ge 0; $index--) {
        $handle = $script:OwnedHandles[$index]
        try {
            if (-not $handle.HasExited) {
                $handle.Terminate()
                [void]$handle.Wait(5000)
            }
        }
        catch { Write-Warning ("Harness cleanup failed for its captured process handle: " + $_.Exception.Message) }
        finally { $handle.Dispose() }
    }
}

$failed = $false
try {
    Assert-True ($env:OS -eq "Windows_NT") "This integration harness requires Windows."
    Assert-True (Test-Path -LiteralPath $PythonExe) "Install the existing project dependencies before this harness; it will not download them."
    Assert-PortsFree
    New-Item -ItemType Directory -Path $OutputDir, $PythonPathDir, $ShimDir -Force | Out-Null
    # create_app is side-effect-free until FastAPI lifespan starts. This keeps
    # the actual Gateway API/Uvicorn with a test-only SQLite path, not data/.
    $sitecustomize = @'
import os
import sys
from importlib import import_module
url = os.environ.get("GATEWAY_RUNNER_TEST_DATABASE_URL")
if url:
    try:
        module = import_module("enterprise_ai_tool_gateway.api.http.app")
        module.app = module.create_app(database_url=url)
        if module.app.state.database_url != url:
            raise RuntimeError("Gateway test database override was not applied")
    except BaseException as error:
        # sitecustomize errors normally do not stop Python. Fail closed so an
        # import/hook problem cannot start the app against its durable default DB.
        print("runner test isolation failed: " + str(error), file=sys.stderr, flush=True)
        os._exit(81)
'@
    [System.IO.File]::WriteAllText((Join-Path $PythonPathDir "sitecustomize.py"), $sitecustomize, $Encoding)
    $listener = @'
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(503)
        self.end_headers()
        self.wfile.write(b"test-owned unrelated service")
    def log_message(self, *args):
        pass
server = HTTPServer(("127.0.0.1", 8000), Handler)
print("test-owned unrelated listener ready", flush=True)
server.serve_forever()
'@
    [System.IO.File]::WriteAllText((Join-Path $OutputDir "unrelated_listener.py"), $listener, $Encoding)
    # The frontend now launches a native node.exe, so the failure fixture must
    # also be an actual executable rather than a shell/batch shim.
    $nodeFixture = @'
using System;
using System.Threading;
namespace Gateway.Demo.Tests
{
    public static class FrontendFailureFixture
    {
        public static int Main(string[] arguments)
        {
            Console.Error.WriteLine("intentional frontend fixture failure");
            Thread.Sleep(500);
            return 7;
        }
    }
}
'@
    Add-Type -TypeDefinition $nodeFixture -OutputAssembly (Join-Path $ShimDir "node.exe") -OutputType ConsoleApplication

    $cases = @($Case)
    if ($Case -eq "All") { $cases = @("CtrlC", "ForcedTermination", "StartupTermination", "Repeat", "Reuse", "OccupiedPort", "PartialStartupFailure") }
    foreach ($selected in $cases) {
        Write-Host "[runner-test] Starting $selected"
        $started = [DateTime]::UtcNow
        try {
            switch ($selected) {
                "CtrlC" { Test-CtrlC }
                "ForcedTermination" { Test-ForcedTermination }
                "StartupTermination" { Test-StartupTermination }
                "Repeat" { for ($cycle = 1; $cycle -le $RepeatCount; $cycle++) { Test-CtrlC ("repeat-" + $cycle) } }
                "Reuse" { Test-Reuse }
                "OccupiedPort" { Test-OccupiedPort }
                "PartialStartupFailure" { Test-PartialStartupFailure }
            }
            [void]$script:Results.Add([pscustomobject]@{ case = $selected; status = "passed"; seconds = ([DateTime]::UtcNow - $started).TotalSeconds })
            Write-Host "[runner-test] Passed $selected"
        }
        catch {
            [void]$script:Results.Add([pscustomobject]@{ case = $selected; status = "failed"; seconds = ([DateTime]::UtcNow - $started).TotalSeconds; error = $_.Exception.Message })
            throw
        }
    }
}
catch {
    $failed = $true
    Write-Host ("[runner-test] FAILED: " + $_.Exception.Message) -ForegroundColor Red
}
finally {
    Stop-HarnessOwnedProcesses
    if (Test-Path -LiteralPath $OutputDir) {
        $report = [ordered]@{
            test_id = $TestId
            cases = @($script:Results)
            backend_port_open_after_cleanup = Test-Port 8000
            frontend_port_open_after_cleanup = Test-Port 5173
            actual_gateway_api_and_frontend = (@($script:Results | Where-Object { $_.status -eq "passed" -and $_.case -in @("CtrlC", "ForcedTermination", "Repeat", "Reuse") }).Count -gt 0)
            database_isolated_by_runtime_sitecustomize = $true
            provider_or_external_api_requests = $false
            ctrl_close_event_or_window_click_verified = $false
            forced_termination_checks_kernel_job_cleanup = (@($script:Results | Where-Object { $_.status -eq "passed" -and $_.case -eq "ForcedTermination" }).Count -gt 0)
            startup_termination_three_cycles_verified = (@($script:Results | Where-Object { $_.status -eq "passed" -and $_.case -eq "StartupTermination" }).Count -gt 0)
            runner_console_logs = @($script:Runners | Select-Object -ExpandProperty ConsoleLog)
            output_directory = $OutputDir
        }
        [System.IO.File]::WriteAllText((Join-Path $OutputDir "summary.json"), ($report | ConvertTo-Json -Depth 6), $Encoding)
        Write-Host "[runner-test] Evidence: $OutputDir"
    }
}
if ($failed) { exit 1 }
Write-Host "[runner-test] All requested cases passed. CTRL_CLOSE_EVENT/window-click was not exercised."
exit 0
