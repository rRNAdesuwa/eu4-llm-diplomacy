@echo off
setlocal EnableDelayedExpansion
if "%~1"=="" exit /b 2
if exist "%~1" exit /b 3
mkdir "%~1"
if errorlevel 1 exit /b 4
set "EU4_SPY_CAPTURE_OUT=%~f1"
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "EU4_SPY_CAPTURE_VS=%%i"
  call "!EU4_SPY_CAPTURE_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 5
)
pushd "%~dp0"
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /c "..\v18-spy-no-send-core-1375\spy_core.cpp" /Fo"%EU4_SPY_CAPTURE_OUT%\spy_core.obj" >"%EU4_SPY_CAPTURE_OUT%\core.stdout" 2>"%EU4_SPY_CAPTURE_OUT%\core.stderr"
if errorlevel 1 (popd & exit /b 6)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc capture_mock.cpp "%EU4_SPY_CAPTURE_OUT%\spy_core.obj" kernel32.lib /Fo"%EU4_SPY_CAPTURE_OUT%\capture.obj" /Fe"%EU4_SPY_CAPTURE_OUT%\capture.exe" /link /INCREMENTAL:NO >"%EU4_SPY_CAPTURE_OUT%\capture.stdout" 2>"%EU4_SPY_CAPTURE_OUT%\capture.stderr"
if errorlevel 1 (popd & exit /b 7)
for %%s in (false mixed true late_cleanup factory_exception final_audit_failure) do (
  "%EU4_SPY_CAPTURE_OUT%\capture.exe" %%s >"%EU4_SPY_CAPTURE_OUT%\%%s.jsonl" 2>"%EU4_SPY_CAPTURE_OUT%\%%s.stderr"
  if errorlevel 1 (popd & exit /b 8)
)
popd
exit /b 0
