$ErrorActionPreference = 'Stop'
# Isolated research build: does not replace the validated peace-lock DLL.
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $PSScriptRoot 'import-local-env.ps1')
Import-ProjectLocalEnv -ProjectRoot $projectRoot
$compiler = Get-ProjectLocalValue -Name 'EU4_CXX'
$compilerArguments = @('-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-fno-exceptions', '-fno-rtti', '-shared', '-static-libgcc', '-static-libstdc++', '-Wl,--no-insert-timestamp', '-DBRIDGE_PEACE_AUTHORITY_LOCK=1', '-DBRIDGE_TRACE_COMMAND_EXECUTION=1', '-DBRIDGE_TRACE_PEACE_RESPONSES=1', '-DBRIDGE_ENABLE_PEACE_SEND=1', '-DBRIDGE_TEST_AI_RECIPIENT=1', '-DBRIDGE_DISPATCH_DIAGNOSTICS=1', '-o', (Join-Path $PSScriptRoot 'eu4_bridge_authorized_peace_v6.dll'), (Join-Path $PSScriptRoot 'authorized-probe-v6.cpp'), (Join-Path $PSScriptRoot 'frame_stub.S'))
& $compiler @compilerArguments
if ($LASTEXITCODE -ne 0) { throw 'Authorized peace research build failed.' }
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PSScriptRoot 'eu4_bridge_authorized_peace_v6.dll')
