@echo off
setlocal EnableDelayedExpansion
if "%~1"=="" exit /b 2
if exist "%~1" exit /b 3
mkdir "%~1"
if errorlevel 1 exit /b 4
set "SPY_BOOT_OUT=%~f1"
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "SPY_BOOT_VS=%%i"
  call "!SPY_BOOT_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 5
)
pushd "%~dp0"
for %%f in (bootstrap installer) do (
  cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /c %%f.cpp /Fo"%SPY_BOOT_OUT%\%%f.obj" >"%SPY_BOOT_OUT%\%%f.stdout" 2>"%SPY_BOOT_OUT%\%%f.stderr"
  if errorlevel 1 (popd & exit /b 6)
)
for %%f in (host journal) do (
  cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /c ..\v19-spy-restricted-host-r2-1375\%%f.cpp /Fo"%SPY_BOOT_OUT%\%%f.obj" >"%SPY_BOOT_OUT%\%%f.stdout" 2>"%SPY_BOOT_OUT%\%%f.stderr"
  if errorlevel 1 (popd & exit /b 7)
)
for %%f in (host native_env) do (
  cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /c ..\v19-spy-restricted-host-r2-1375\preflight\%%f.cpp /Fo"%SPY_BOOT_OUT%\preflight-%%f.obj" >"%SPY_BOOT_OUT%\preflight-%%f.stdout" 2>"%SPY_BOOT_OUT%\preflight-%%f.stderr"
  if errorlevel 1 (popd & exit /b 8)
)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /c ..\v19-spy-restricted-host-r2-1375\core\v18-preimage\spy_core.cpp /Fo"%SPY_BOOT_OUT%\preflight-core.obj" >"%SPY_BOOT_OUT%\preflight-core.stdout" 2>"%SPY_BOOT_OUT%\preflight-core.stderr"
if errorlevel 1 (popd & exit /b 9)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /c ..\v19-spy-restricted-host-r2-1375\core\spy_send_core.cpp /Fo"%SPY_BOOT_OUT%\send-core.obj" >"%SPY_BOOT_OUT%\send-core.stdout" 2>"%SPY_BOOT_OUT%\send-core.stderr"
if errorlevel 1 (popd & exit /b 10)
ml64 /nologo /c /Fo"%SPY_BOOT_OUT%\frame.obj" frame.asm >"%SPY_BOOT_OUT%\frame.stdout" 2>"%SPY_BOOT_OUT%\frame.stderr"
if errorlevel 1 (popd & exit /b 11)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc test_bootstrap.cpp /Fo"%SPY_BOOT_OUT%\test_bootstrap.obj" /Fe"%SPY_BOOT_OUT%\test_bootstrap.exe" /link /INCREMENTAL:NO >"%SPY_BOOT_OUT%\test-compile.stdout" 2>"%SPY_BOOT_OUT%\test-compile.stderr"
if errorlevel 1 (popd & exit /b 12)
"%SPY_BOOT_OUT%\test_bootstrap.exe" >"%SPY_BOOT_OUT%\test.stdout" 2>"%SPY_BOOT_OUT%\test.stderr"
if errorlevel 1 (popd & exit /b 13)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc test_claims.cpp /Fo"%SPY_BOOT_OUT%\test_claims.obj" /Fe"%SPY_BOOT_OUT%\test_claims.exe" /link /INCREMENTAL:NO "%SPY_BOOT_OUT%\installer.obj" "%SPY_BOOT_OUT%\host.obj" "%SPY_BOOT_OUT%\journal.obj" "%SPY_BOOT_OUT%\preflight-host.obj" "%SPY_BOOT_OUT%\preflight-native_env.obj" "%SPY_BOOT_OUT%\preflight-core.obj" "%SPY_BOOT_OUT%\send-core.obj" "%SPY_BOOT_OUT%\frame.obj" kernel32.lib user32.lib advapi32.lib bcrypt.lib >"%SPY_BOOT_OUT%\claim-compile.stdout" 2>"%SPY_BOOT_OUT%\claim-compile.stderr"
if errorlevel 1 (popd & exit /b 14)
"%SPY_BOOT_OUT%\test_claims.exe" >"%SPY_BOOT_OUT%\claims.stdout" 2>"%SPY_BOOT_OUT%\claims.stderr"
if errorlevel 1 (popd & exit /b 15)
link /nologo /DLL /MACHINE:X64 /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT /OUT:"%SPY_BOOT_OUT%\eu4_spy_send_lab_1375_v19.dll" "%SPY_BOOT_OUT%\bootstrap.obj" "%SPY_BOOT_OUT%\installer.obj" "%SPY_BOOT_OUT%\host.obj" "%SPY_BOOT_OUT%\journal.obj" "%SPY_BOOT_OUT%\preflight-host.obj" "%SPY_BOOT_OUT%\preflight-native_env.obj" "%SPY_BOOT_OUT%\preflight-core.obj" "%SPY_BOOT_OUT%\send-core.obj" "%SPY_BOOT_OUT%\frame.obj" kernel32.lib user32.lib advapi32.lib bcrypt.lib >"%SPY_BOOT_OUT%\link.stdout" 2>"%SPY_BOOT_OUT%\link.stderr"
set "SPY_BOOT_RESULT=!errorlevel!"
popd
exit /b !SPY_BOOT_RESULT!
