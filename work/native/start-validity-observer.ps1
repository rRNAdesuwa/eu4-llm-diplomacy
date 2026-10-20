param([switch]$SavedTestGame)
$ErrorActionPreference = 'Stop'
if (-not $SavedTestGame) { throw 'Use a separate saved experiment; pass -SavedTestGame.' }
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $PSScriptRoot 'import-local-env.ps1')
Import-ProjectLocalEnv -ProjectRoot $projectRoot
$python = Get-ProjectLocalValue -Name 'EU4_PYTHON'
$gameExe = Join-Path (Get-ProjectLocalValue -Name 'EU4_GAME_ROOT') 'eu4.exe'
$dll = Join-Path $PSScriptRoot 'eu4_bridge_authorized_peace_v7.dll'
$expectedDllHash = 'F989A4DE0BA60C1285907752179DD9626AEA2611ED1A1A42771410BF0952FAD3'
if ((Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash -ne $expectedDllHash) { throw 'DLL differs from reviewed research build.' }
$instances = @(Get-CimInstance Win32_Process -Filter "Name='eu4.exe'")
if ($instances.Count -ne 1 -or $instances[0].ExecutablePath -ne $gameExe) { throw 'Expected exactly one matching EU4 process.' }
$gamePid = $instances[0].ProcessId
$statePath = Join-Path $PSScriptRoot '..\runtime\authorized-v7-preflight.json'
& $python -B (Join-Path $PSScriptRoot '..\probe_native_state.py') --pid $gamePid --output $statePath
if ($LASTEXITCODE -ne 0) { throw 'Read-only process preflight failed; no DLL installed.' }
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if ($state.player_tag -ne 'POR') { throw 'AI-recipient experiment requires player POR; no DLL installed.' }
$fra = @($state.consistent_slots | Where-Object { $_.slot -eq 122 -and $_.tag -eq 'FRA' -and $_.index_matches_slot })
$eng = @($state.consistent_slots | Where-Object { $_.slot -eq 46 -and $_.tag -eq 'ENG' -and $_.index_matches_slot })
if ($fra.Count -ne 1 -or $eng.Count -ne 1) { throw 'Country identities not established; no DLL installed.' }
& $python -B (Join-Path $PSScriptRoot 'inject_probe.py') --pid $gamePid --dll $dll --ack-test-save
if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Do not retry in this game process.' }
Write-Output 'Installed research authorization mode. No peace request generated; inspect authorization_selftest_passed before sending.'
