@echo off
setlocal EnableDelayedExpansion
if "%~1"=="" exit /b 2
if exist "%~1" exit /b 3
mkdir "%~1"
if errorlevel 1 exit /b 4
set "EU4_SPY19_OUT=%~f1"
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "EU4_SPY19_VS=%%i"
  call "!EU4_SPY19_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 5
)
pushd "%~dp0"
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /c spy_send_core.cpp /Fo"%EU4_SPY19_OUT%\spy_send_core.obj" >"%EU4_SPY19_OUT%\core.stdout" 2>"%EU4_SPY19_OUT%\core.stderr"
if errorlevel 1 (popd & exit /b 6)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc test_spy_send_core.cpp "%EU4_SPY19_OUT%\spy_send_core.obj" kernel32.lib /Fo"%EU4_SPY19_OUT%\test_spy_send_core.obj" /Fe"%EU4_SPY19_OUT%\test_spy_send_core.exe" /link /INCREMENTAL:NO >"%EU4_SPY19_OUT%\mock.stdout" 2>"%EU4_SPY19_OUT%\mock.stderr"
if errorlevel 1 (popd & exit /b 7)
"%EU4_SPY19_OUT%\test_spy_send_core.exe" >"%EU4_SPY19_OUT%\test.stdout" 2>"%EU4_SPY19_OUT%\test.stderr"
set "EU4_SPY19_RESULT=!errorlevel!"
popd
exit /b !EU4_SPY19_RESULT!
