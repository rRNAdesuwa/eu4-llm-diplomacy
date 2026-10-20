@echo off
setlocal EnableDelayedExpansion
if "%~1"=="" exit /b 2
if exist "%~1" exit /b 3
mkdir "%~1"
if errorlevel 1 exit /b 4
set "SPY19_HOST_OUT=%~f1"
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "SPY19_HOST_VS=%%i"
  call "!SPY19_HOST_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 5
)
pushd "%~dp0"
for %%f in (host journal) do (
  cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /c %%f.cpp /Fo"%SPY19_HOST_OUT%\%%f.obj" >"%SPY19_HOST_OUT%\%%f.stdout" 2>"%SPY19_HOST_OUT%\%%f.stderr"
  if errorlevel 1 (popd & exit /b 6)
)
for %%f in (host native_env) do (
  cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /c preflight\%%f.cpp /Fo"%SPY19_HOST_OUT%\preflight-%%f.obj" >"%SPY19_HOST_OUT%\preflight-%%f.stdout" 2>"%SPY19_HOST_OUT%\preflight-%%f.stderr"
  if errorlevel 1 (popd & exit /b 7)
)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /c core\v18-preimage\spy_core.cpp /Fo"%SPY19_HOST_OUT%\preflight-core.obj" >"%SPY19_HOST_OUT%\preflight-core.stdout" 2>"%SPY19_HOST_OUT%\preflight-core.stderr"
if errorlevel 1 (popd & exit /b 8)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /c core\spy_send_core.cpp /Fo"%SPY19_HOST_OUT%\send-core.obj" >"%SPY19_HOST_OUT%\send-core.stdout" 2>"%SPY19_HOST_OUT%\send-core.stderr"
if errorlevel 1 (popd & exit /b 9)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc test_host.cpp "%SPY19_HOST_OUT%\host.obj" "%SPY19_HOST_OUT%\journal.obj" "%SPY19_HOST_OUT%\preflight-host.obj" "%SPY19_HOST_OUT%\preflight-core.obj" "%SPY19_HOST_OUT%\send-core.obj" kernel32.lib advapi32.lib /Fo"%SPY19_HOST_OUT%\test_host.obj" /Fe"%SPY19_HOST_OUT%\test_host.exe" /link /INCREMENTAL:NO >"%SPY19_HOST_OUT%\mock.stdout" 2>"%SPY19_HOST_OUT%\mock.stderr"
if errorlevel 1 (popd & exit /b 10)
"%SPY19_HOST_OUT%\test_host.exe" "%SPY19_HOST_OUT%\mock-events.jsonl" >"%SPY19_HOST_OUT%\test.stdout" 2>"%SPY19_HOST_OUT%\test.stderr"
set "SPY19_HOST_RESULT=!errorlevel!"
popd
exit /b !SPY19_HOST_RESULT!
