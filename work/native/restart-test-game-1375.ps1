param(
    [Parameter(Mandatory = $true)][int]$ExpectedPid,
    [Parameter(Mandatory = $true)][ValidatePattern('^llm_[A-Za-z0-9_-]+\.eu4$')][string]$SaveName,
    [Parameter(Mandatory = $true)][switch]$SavedTestGame,
    [switch]$PlanOnly
)
$ErrorActionPreference = 'Stop'
if (-not $SavedTestGame -or $ExpectedPid -le 0) { throw 'An identified disposable saved test game is required.' }
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $PSScriptRoot 'import-local-env.ps1')
. (Join-Path $PSScriptRoot 'restart-arguments-1375.ps1')
Import-ProjectLocalEnv -ProjectRoot $projectRoot
$expectedExe = [IO.Path]::GetFullPath((Join-Path (Get-ProjectLocalValue -Name 'EU4_GAME_ROOT') 'eu4.exe'))
$expectedHash = '9AD3EFE1AF169F40EE577F9DAE5DEBBC87AF6FB8B5450FB345EBF110DC4D771A'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $expectedExe).Hash -ne $expectedHash) {
    throw 'Executable differs from the audited EU4 1.37.5 build; no process was stopped.'
}
$saveRoot = [IO.Path]::GetFullPath((Join-Path (Get-ProjectLocalValue -Name 'EU4_USER_DATA') 'save games'))
$savePath = [IO.Path]::GetFullPath((Join-Path $saveRoot $SaveName))
if (-not $savePath.StartsWith($saveRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Save must remain within the game user-data save directory.'
}
$save = Get-Item -LiteralPath $savePath
if ($save.PSIsContainer -or ($save.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $save.Length -lt 100) {
    throw 'Expected a regular, nonempty test save; no process was stopped.'
}
$saveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $savePath).Hash
$instances = @(Get-CimInstance Win32_Process -Filter "name='eu4.exe'")
if ($instances.Count -ne 1 -or $instances[0].ProcessId -ne $ExpectedPid) {
    throw 'The single expected EU4 process is no longer current; no process was stopped.'
}
$instance = $instances[0]
if (-not [String]::Equals($instance.ExecutablePath, $expectedExe, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Unexpected process image path; no process was stopped.'
}
if ($instance.CommandLine -notmatch '^\s*(?:"[^"]*"|\S+)(?:\s+(.*))?$') {
    throw 'Cannot preserve original launch arguments; no process was stopped.'
}
# Preserve launch credentials locally in memory only. Never print the command
# line or write launcher/session tokens to a report.
$originalArguments = $Matches[1]
$launchArguments = ConvertTo-TestRestartArguments -Arguments $originalArguments -SaveName $SaveName
$result = [ordered]@{
    purpose = 'disposable_1375_test_restart'
    expected_pid = $ExpectedPid
    executable_sha256 = $expectedHash
    save = $savePath
    save_sha256 = $saveHash
    original_creation_time = $instance.CreationDate.ToUniversalTime().ToString('o')
    startup_option = '-continue=<verified test filename>'
    plan_only = [bool]$PlanOnly
    loaded_save_verified = $false
}
if ($PlanOnly) { $result | ConvertTo-Json; return }
# Recheck PID creation and save identity immediately before closing this exact
# test process. The caller is intentionally discarding this disposable state.
$gameProcess = Get-Process -Id $ExpectedPid
$forced = $false
try {
    # Pin this Process object's native handle before the last identity check;
    # forced termination uses that object, never a new lookup by PID.
    [void]$gameProcess.Handle
    $fresh = Get-CimInstance Win32_Process -Filter "ProcessId=$ExpectedPid"
    if (-not $fresh -or $fresh.CreationDate -ne $instance.CreationDate -or
        (Get-FileHash -Algorithm SHA256 -LiteralPath $savePath).Hash -ne $saveHash) {
        throw 'Process or test save changed since preflight; no process was stopped.'
    }
    $requested = $gameProcess.CloseMainWindow()
    if (-not $requested -or -not $gameProcess.WaitForExit(8000)) {
        $stillCurrent = Get-CimInstance Win32_Process -Filter "ProcessId=$ExpectedPid"
        if ($stillCurrent -and $stillCurrent.CreationDate -ne $instance.CreationDate) {
            throw 'PID was reused while closing; refusing to stop its new owner.'
        }
        if ($stillCurrent) {
            $gameProcess.Kill()
            if (-not $gameProcess.WaitForExit(15000)) { throw 'Test process did not finish exiting; no second game was started.' }
            $forced = $true
        }
    }
} finally {
    $gameProcess.Dispose()
}
# A direct child of PowerShell does not inherit the Steam launcher AppId.
# Supply only this installed application's context to its new process; Steam
# still performs normal client/account/license initialization.
$newGame = Start-Process -FilePath $expectedExe -WorkingDirectory (Split-Path -Parent $expectedExe) -ArgumentList $launchArguments -Environment @{ SteamAppId = '236850'; SteamGameId = '236850' } -WindowStyle Hidden -PassThru
$result['forced_test_process_exit'] = $forced
$result['new_pid'] = $newGame.Id
$result['launched_at_utc'] = [DateTime]::UtcNow.ToString('o')
$reportPath = Join-Path $projectRoot ('work\runtime\test-restart-1375-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '.json')
$result | ConvertTo-Json | Set-Content -LiteralPath $reportPath -Encoding UTF8
$result['report'] = $reportPath
$result | ConvertTo-Json
# Startup can take time. This script never injects or assumes that the requested
# file was loaded. Verify player, date, relations and process identity afterward.
