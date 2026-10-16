param([string]$OutputName = 'eu4_bridge_probe.dll', [switch]$EnablePeaceSend, [switch]$TestAIRecipient, [switch]$TracePeaceResponses, [switch]$DispatchDiagnostics, [switch]$TraceCommandExecution, [switch]$PeaceAuthorityLock)
$ErrorActionPreference = 'Stop'
if ($TraceCommandExecution -and -not $TracePeaceResponses) { throw 'Command execution tracing requires the trace infrastructure switch.' }
if ($PeaceAuthorityLock -and (-not $TraceCommandExecution -or $EnablePeaceSend)) { throw 'Peace quarantine requires command tracing and must not enable bridge sending.' }
$nativeSourceDirectory = $PSScriptRoot
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $PSScriptRoot 'import-local-env.ps1')
Import-ProjectLocalEnv -ProjectRoot $projectRoot
$nativeCompiler = Get-ProjectLocalValue -Name 'EU4_CXX'
$nativeCompilerArguments = @('-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-fno-exceptions', '-fno-rtti', '-shared', '-static-libgcc', '-static-libstdc++', '-Wl,--no-insert-timestamp')
if ($EnablePeaceSend) { $nativeCompilerArguments += '-DBRIDGE_ENABLE_PEACE_SEND=1' }
if ($TestAIRecipient) { $nativeCompilerArguments += '-DBRIDGE_TEST_AI_RECIPIENT=1' }
if ($TracePeaceResponses) { $nativeCompilerArguments += '-DBRIDGE_TRACE_PEACE_RESPONSES=1' }
if ($DispatchDiagnostics) { $nativeCompilerArguments += '-DBRIDGE_DISPATCH_DIAGNOSTICS=1' }
if ($TraceCommandExecution) { $nativeCompilerArguments += '-DBRIDGE_TRACE_COMMAND_EXECUTION=1' }
if ($PeaceAuthorityLock) { $nativeCompilerArguments += '-DBRIDGE_PEACE_AUTHORITY_LOCK=1' }
$nativeCompilerArguments += @('-o', (Join-Path $nativeSourceDirectory $OutputName), (Join-Path $nativeSourceDirectory 'probe.cpp'), (Join-Path $nativeSourceDirectory 'frame_stub.S'))
& $nativeCompiler @nativeCompilerArguments
if ($LASTEXITCODE -ne 0) { throw 'Native probe build failed' }
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $nativeSourceDirectory $OutputName)
