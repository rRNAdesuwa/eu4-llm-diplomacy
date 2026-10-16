param([switch]$SavedTestGame)
$ErrorActionPreference = 'Stop'
if (-not $SavedTestGame) { throw 'Use a separate saved experiment; pass -SavedTestGame.' }
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $PSScriptRoot 'import-local-env.ps1')
Import-ProjectLocalEnv -ProjectRoot $projectRoot
$python = Get-ProjectLocalValue -Name 'EU4_PYTHON'
$gameExe = Join-Path (Get-ProjectLocalValue -Name 'EU4_GAME_ROOT') 'eu4.exe'
& $python -B (Join-Path $PSScriptRoot '..\prepare_automatic_war.py')
if ($LASTEXITCODE -ne 0) { throw 'Fixed war script preparation failed.' }
$dll = Join-Path $PSScriptRoot 'eu4_bridge_automated_diplomacy_v9.dll'
$expectedDllHash = '1440F664C397C6CA4CE501010BA035DB8D9119EC6BAD5E8FE2F214D1775C28B3'
if ((Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash -ne $expectedDllHash) { throw 'DLL differs from reviewed research build.' }
$instances = @(Get-CimInstance Win32_Process -Filter "Name='eu4.exe'")
if ($instances.Count -ne 1 -or $instances[0].ExecutablePath -ne $gameExe) { throw 'Expected exactly one matching EU4 process.' }
$gamePid = $instances[0].ProcessId
$statePath = Join-Path $PSScriptRoot '..\runtime\automated-diplomacy-preflight.json'
& $python -B (Join-Path $PSScriptRoot '..\probe_native_state.py') --pid $gamePid --output $statePath
if ($LASTEXITCODE -ne 0) { throw 'Read-only process preflight failed; no DLL installed.' }
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if ($state.player_tag -ne 'POR') { throw 'AI-recipient experiment requires player POR; no DLL installed.' }
$fra = @($state.consistent_slots | Where-Object { $_.slot -eq 122 -and $_.tag -eq 'FRA' -and $_.index_matches_slot })
$eng = @($state.consistent_slots | Where-Object { $_.slot -eq 46 -and $_.tag -eq 'ENG' -and $_.index_matches_slot })
if ($fra.Count -ne 1 -or $eng.Count -ne 1) { throw 'Country identities not established; no DLL installed.' }
& $python -B (Join-Path $PSScriptRoot 'inject_probe.py') --pid $gamePid --dll $dll --ack-test-save
if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Do not retry in this game process.' }
Write-Output 'Installed v9 automatic war and authorized peace. No request generated; peace selftest waits for a live FRA-ENG war.'
