@echo off
setlocal EnableDelayedExpansion
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "EU4_FIXTURE_TEST_VS=%%i"
  call "!EU4_FIXTURE_TEST_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 1
)
pushd "%~dp0"
if not exist "..\..\runtime\native1375-v9-baseline-test" mkdir "..\..\runtime\native1375-v9-baseline-test"
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\..\runtime\native1375-v9-baseline-test\test.obj" /Fe"..\..\runtime\native1375-v9-baseline-test\test.exe" test_fixture_baseline.cpp kernel32.lib
if errorlevel 1 (popd & exit /b 1)
"..\..\runtime\native1375-v9-baseline-test\test.exe"
set "EU4_FIXTURE_TEST_RESULT=!errorlevel!"
popd
exit /b !EU4_FIXTURE_TEST_RESULT!
