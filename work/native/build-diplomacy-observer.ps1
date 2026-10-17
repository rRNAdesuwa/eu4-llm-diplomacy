param([ValidatePattern('^[A-Za-z0-9_-]+$')][string]$Experiment = 'alliance-observer-20261013', [switch]$ReasonMetadata)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $PSScriptRoot 'import-local-env.ps1')
Import-ProjectLocalEnv -ProjectRoot $projectRoot
$outputDirectory = Join-Path $projectRoot ('work\runtime\' + $Experiment)
if (Test-Path -LiteralPath $outputDirectory) { throw 'Use a new experiment directory; existing evidence is immutable.' }
New-Item -ItemType Directory -Path $outputDirectory | Out-Null
$dll = Join-Path $outputDirectory 'eu4_bridge_diplomacy_observer_v22.dll'
$arguments = @('-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-fno-exceptions', '-fno-rtti',
    '-shared', '-static-libgcc', '-static-libstdc++', '-Wl,--no-insert-timestamp',
    '-o', $dll, (Join-Path $PSScriptRoot 'diplomacy-observer-v10.cpp'), (Join-Path $PSScriptRoot 'frame_stub.S'))
if ($ReasonMetadata) { $arguments = @('-DBRIDGE_ALLIANCE_REASON_METADATA=1') + $arguments }
& (Get-ProjectLocalValue -Name 'EU4_CXX') @arguments
if ($LASTEXITCODE -ne 0) { throw 'Observer build failed; directory retained as failed evidence.' }
$sourceNames = @('diplomacy-observer-v10.cpp','alliance-query.inc','insult-query.inc','rival-query.inc','vassal-query.inc','declarewar-query.inc','peace-context-query.inc','peace-empty-offer-query.inc','peace-offer-evaluation-query.inc','peace-money-query.inc','peace-war-context-query.inc','peace-payload.h','peace-native-payload.inc','peace-province-candidates.inc','peace-province-selection.inc','declarewar-payload.h','declarewar-native-payload.inc','declarewar-execution-preflight.inc','declarewar-execution-state.inc','declarewar-cost-query.inc','declarewar-candidates.inc','vassal-test-context.inc','vassal-test-context-script.h','vassal-inbound-test-context.inc','vassal-inbound-test-context-script.h','rival-authority.inc','rival-command-observer.inc','rival-execution.inc','rival-command-authority.h','rival-command-wire.h','alliance-reason-metadata.inc','alliance-reason-metadata-bind.inc','alliance-reason-key-branch.h','alliance-reason-row.h','alliance-lifecycle.inc','alliance-entry-observer.inc','alliance-protocol-observer.inc','alliance-transport.inc','alliance-authority-ledger.h','alliance-execution-wire.h','alliance-inbound-response-wire.h','alliance-inbound-inspection-event.h','alliance-pending-membership.h','alliance-inbound.inc','inbound-pending-recovery.inc','alliance-execution.inc','entry-patch-transaction.inc','control-probe.cpp','automated-control.inc','popup-control.inc','frame_stub.S')
$sourceNames += @('peace-payload-ref.h','peace-action-native-payload.inc','peace-lifecycle-hooks.inc','peace-execution-preflight.inc','peace-handler-authority.inc')
$sourceNames += @('peace-execution-wire.h','peace-execution.inc','peace-inbound-context.inc')
$sourceNames += @('peace-receiver-observer.inc')
$sourceNames += @('peace-wrapper-rule-query.inc')
$sourceNames += @('peace-effects.h','peace-effect-state.inc')
$sources = foreach ($name in $sourceNames) {
    $source = Join-Path $PSScriptRoot $name
    Copy-Item -LiteralPath $source -Destination (Join-Path $outputDirectory $name)
    [ordered]@{ name = $name; sha256 = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() }
}
$game = Join-Path (Get-ProjectLocalValue -Name 'EU4_GAME_ROOT') 'eu4.exe'
[ordered]@{ version = 22; experiment_id = $Experiment; compiled = $true; runtime_verified = $false; reason_metadata_requested = [bool]$ReasonMetadata
    game_sha256 = (Get-FileHash -LiteralPath $game -Algorithm SHA256).Hash.ToLowerInvariant()
    dll_sha256 = (Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant()
    dll = $dll; sources = @($sources); compiler_arguments = $arguments } |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $outputDirectory 'build-manifest.json') -Encoding UTF8
Get-FileHash -LiteralPath $dll -Algorithm SHA256
