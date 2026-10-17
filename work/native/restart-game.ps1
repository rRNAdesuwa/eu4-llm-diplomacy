param([switch]$SavedTestGame, [ValidatePattern('^[A-Za-z0-9_-]+\.eu4$')][string]$SaveName)
$ErrorActionPreference = 'Stop'
if (-not $SavedTestGame) { throw 'Restart is for the separate saved test game; pass -SavedTestGame.' }
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $PSScriptRoot 'import-local-env.ps1')
Import-ProjectLocalEnv -ProjectRoot $projectRoot
$expectedExe = Join-Path (Get-ProjectLocalValue -Name 'EU4_GAME_ROOT') 'eu4.exe'
$expectedHash = 'B23FA0E1F698D31B01CDD1C3817A675805D8C6286CB66F9C231E6E2A42544D77'
if ($SaveName) {
    $savePath = Join-Path (Join-Path (Get-ProjectLocalValue -Name 'EU4_USER_DATA') 'save games') $SaveName
    if (-not (Test-Path -LiteralPath $savePath -PathType Leaf)) { throw 'Requested test save does not exist; no process was stopped.' }
}
$launchRecordPath = Join-Path $PSScriptRoot '..\runtime\game-launch.json'
$gameInstances = @(Get-CimInstance Win32_Process -Filter "name='eu4.exe'")
if ($gameInstances.Count -gt 1) { throw 'Multiple EU4 instances; no process was stopped.' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $expectedExe).Hash -ne $expectedHash) {
    throw 'Game executable differs from the tested build.'
}
if ($gameInstances.Count -eq 1) {
    $gameInstance = $gameInstances[0]
    if ($gameInstance.ExecutablePath -ne $expectedExe) { throw 'Unexpected game executable; no process was stopped.' }
    if ($gameInstance.CommandLine -notmatch '^\s*(?:"[^"]*"|\S+)(?:\s+(.*))?$') {
        throw 'Cannot preserve original launch arguments; no process was stopped.'
    }
    $originalArguments = $Matches[1]
    [ordered]@{ executable = $expectedExe; arguments = $originalArguments } |
        ConvertTo-Json | Set-Content -LiteralPath $launchRecordPath -Encoding UTF8
    $gameProcess = Get-Process -Id $gameInstance.ProcessId
    $closeRequested = $gameProcess.CloseMainWindow()
    if (-not $closeRequested -or -not $gameProcess.WaitForExit(8000)) {
        # Explicitly scoped restart: never stop a process selected only by name.
        try {
            $gameProcess.Kill()
        } catch {
            # The graceful close can finish between WaitForExit and Kill.
            if (-not $gameProcess.HasExited) { throw }
        }
        $gameProcess.WaitForExit()
    }
} else {
    if (-not (Test-Path -LiteralPath $launchRecordPath)) { throw 'No existing game or saved launch arguments.' }
    $previousLaunch = Get-Content -LiteralPath $launchRecordPath -Raw | ConvertFrom-Json
    if ($previousLaunch.executable -ne $expectedExe) { throw 'Unexpected saved executable.' }
    $originalArguments = $previousLaunch.arguments
}
$launchParameters = @{
    FilePath = $expectedExe
    WorkingDirectory = Split-Path -Parent $expectedExe
    PassThru = $true
    WindowStyle = 'Normal'
}
if ($SaveName) {
    # Explicit target must take precedence over either saved continue option.
    $originalArguments = [regex]::Replace($originalArguments, '(?i)(?<!\S)-(?:continue=(?:"[^"]*"|\S+)|continuelastsave)(?=\s|$)', '').Trim()
    $originalArguments = ($originalArguments + ' -continue=' + $SaveName).Trim()
}
if ($originalArguments) { $launchParameters.ArgumentList = $originalArguments }
$newGame = Start-Process @launchParameters
Write-Output ('Game restarted; new PID: ' + $newGame.Id)
if ($SaveName) { Write-Output ('Requested startup save: ' + $SaveName + '. Verify loaded state before installing a DLL.') }
else { Write-Output 'Original launch arguments preserved. Load the test save; DLL installation is a separate step.' }
