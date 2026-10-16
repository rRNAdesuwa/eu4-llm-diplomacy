param([switch]$SavedTestGame, [switch]$Lifecycle, [switch]$Sender, [switch]$WarContext, [switch]$RepairedSender, [switch]$GoldSender, [switch]$AIRecipient, [switch]$AIResponseTrace, [switch]$AIDispatchTrace, [switch]$AIExecutionTrace, [switch]$PeaceAuthorityLock)
$ErrorActionPreference = 'Stop'
if (-not $SavedTestGame) { throw 'Save a separate test game first, then pass -SavedTestGame.' }
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $PSScriptRoot 'import-local-env.ps1')
Import-ProjectLocalEnv -ProjectRoot $projectRoot
$nativeGameProcesses = @(Get-Process eu4 -ErrorAction Stop)
if ($nativeGameProcesses.Count -ne 1) { throw 'Expected exactly one eu4 process.' }
$nativePython = Get-ProjectLocalValue -Name 'EU4_PYTHON'
if (([int]$Lifecycle.IsPresent + [int]$Sender.IsPresent + [int]$WarContext.IsPresent + [int]$RepairedSender.IsPresent + [int]$GoldSender.IsPresent + [int]$AIRecipient.IsPresent + [int]$AIResponseTrace.IsPresent + [int]$AIDispatchTrace.IsPresent + [int]$AIExecutionTrace.IsPresent + [int]$PeaceAuthorityLock.IsPresent) -gt 1) { throw 'Select only one probe build.' }
if ($Sender -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'SEND_DISABLED'))) {
    throw 'Sender testing is disabled after the observed crash. Repair and review the offer initialization before re-enabling.'
}
$nativeDllName = if ($PeaceAuthorityLock) { 'eu4_bridge_peace_lock_v1.dll' } elseif ($AIExecutionTrace) { 'eu4_bridge_execution_v1.dll' } elseif ($AIDispatchTrace) { 'eu4_bridge_dispatch_v1.dll' } elseif ($AIResponseTrace) { 'eu4_bridge_ai_response_trace.dll' } elseif ($AIRecipient) { 'eu4_bridge_ai_response.dll' } elseif ($GoldSender) { 'eu4_bridge_gold_v2.dll' } elseif ($RepairedSender) { 'eu4_bridge_sender_repaired.dll' } elseif ($WarContext) { 'eu4_bridge_warcontext.dll' } elseif ($Sender) { 'eu4_bridge_sender.dll' } elseif ($Lifecycle) { 'eu4_bridge_lifecycle.dll' } else { 'eu4_bridge_probe.dll' }
$nativeDllPath = Join-Path $PSScriptRoot $nativeDllName
if ($RepairedSender -and (Get-FileHash -Algorithm SHA256 -LiteralPath $nativeDllPath).Hash -ne '1481E6993653757ECC3244E251AAE1595DC42986EEB7377316DF12B1D181F193') {
    throw 'Repaired sender hash differs from the reviewed build.'
}
if ($GoldSender -and (Get-FileHash -Algorithm SHA256 -LiteralPath $nativeDllPath).Hash -ne 'B4EA6EEA06753909F8CC6D2F5D135468112E85116FC7F2F3A93CAF9E46D6DB84') {
    throw 'Gold sender hash differs from the reviewed build.'
}
if ($AIRecipient -and (Get-FileHash -Algorithm SHA256 -LiteralPath $nativeDllPath).Hash -ne '2225FE321A703BCED28C6BE2E633779E98F6D5730EC8E69903FED6D8A449188C') {
    throw 'AI-recipient test DLL hash differs from the reviewed build.'
}
if ($AIResponseTrace -and (Get-FileHash -Algorithm SHA256 -LiteralPath $nativeDllPath).Hash -ne 'A86295DD111E69673136E9695999F09CA01226CA260AD6DE837CA2F2DC6F5489') {
    throw 'Response trace DLL hash differs from the reviewed build.'
}
if ($AIDispatchTrace -and (Get-FileHash -Algorithm SHA256 -LiteralPath $nativeDllPath).Hash -ne '0C031D88DF66C87DEFD9A534928441E3FF49C4BBF88BDD7BB56525EF7081D70C') {
    throw 'Dispatch diagnostic DLL hash differs from the reviewed build.'
}
if ($AIExecutionTrace -and (Get-FileHash -Algorithm SHA256 -LiteralPath $nativeDllPath).Hash -ne '92A44ABBF4EA0F6B95050377CA25D610EE793ADD45C846F33E7D222BA23FBB05') {
    throw 'Command execution trace DLL hash differs from the reviewed build.'
}
if ($PeaceAuthorityLock -and (Get-FileHash -Algorithm SHA256 -LiteralPath $nativeDllPath).Hash -ne '230A6A81153D1CE6D2B94113126A87E7AA1421A245437C38465889C9C545105F') {
    throw 'Peace authority lock DLL hash differs from the reviewed build.'
}
& $nativePython (Join-Path $PSScriptRoot 'inject_probe.py') --pid $nativeGameProcesses[0].Id --dll $nativeDllPath --ack-test-save
if ($LASTEXITCODE -ne 0) { throw 'Probe installation failed; do not retry in the same game process.' }
$nativeMode = if ($PeaceAuthorityLock) { 'peace quarantine' } else { 'observe' }
Write-Output ('Probe installed in ' + $nativeMode + ' mode. Log: ' + (Join-Path $PSScriptRoot 'probe.jsonl'))
