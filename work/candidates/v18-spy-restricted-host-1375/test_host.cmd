@echo off
setlocal EnableDelayedExpansion
if "%~1"=="" exit /b 2
if exist "%~1" exit /b 3
mkdir "%~1"
if errorlevel 1 exit /b 4
set "SPY_HOST_OUT=%~f1"
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "SPY_HOST_VS=%%i"
  call "!SPY_HOST_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 5
)
pushd "%~dp0"
for %%f in (host journal native_env) do (
  cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /c %%f.cpp /Fo"%SPY_HOST_OUT%\%%f.obj" >"%SPY_HOST_OUT%\%%f.stdout" 2>"%SPY_HOST_OUT%\%%f.stderr"
  if errorlevel 1 (popd & exit /b 6)
)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /c ..\v18-spy-no-send-core-1375\spy_core.cpp /Fo"%SPY_HOST_OUT%\spy_core.obj" >"%SPY_HOST_OUT%\core.stdout" 2>"%SPY_HOST_OUT%\core.stderr"
if errorlevel 1 (popd & exit /b 7)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc test_host.cpp "%SPY_HOST_OUT%\spy_core.obj" "%SPY_HOST_OUT%\host.obj" "%SPY_HOST_OUT%\journal.obj" kernel32.lib advapi32.lib /Fo"%SPY_HOST_OUT%\test_host.obj" /Fe"%SPY_HOST_OUT%\test_host.exe" /link /INCREMENTAL:NO >"%SPY_HOST_OUT%\mock.stdout" 2>"%SPY_HOST_OUT%\mock.stderr"
if errorlevel 1 (popd & exit /b 8)
"%SPY_HOST_OUT%\test_host.exe" "%SPY_HOST_OUT%\mock-events.jsonl" >"%SPY_HOST_OUT%\test.stdout" 2>"%SPY_HOST_OUT%\test.stderr"
set "SPY_HOST_RESULT=!errorlevel!"
if not "!SPY_HOST_RESULT!"=="0" (popd & exit /b !SPY_HOST_RESULT!)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc test_memory.cpp "%SPY_HOST_OUT%\native_env.obj" kernel32.lib bcrypt.lib user32.lib /Fo"%SPY_HOST_OUT%\test_memory.obj" /Fe"%SPY_HOST_OUT%\test_memory.exe" /link /INCREMENTAL:NO >"%SPY_HOST_OUT%\memory-compile.stdout" 2>"%SPY_HOST_OUT%\memory-compile.stderr"
if errorlevel 1 (popd & exit /b 9)
"%SPY_HOST_OUT%\test_memory.exe" >"%SPY_HOST_OUT%\memory.stdout" 2>"%SPY_HOST_OUT%\memory.stderr"
set "SPY_HOST_RESULT=!errorlevel!"
popd
exit /b !SPY_HOST_RESULT!
