@echo off
setlocal EnableDelayedExpansion
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "EU4_CONSUME_TEST_VS=%%i"
  call "!EU4_CONSUME_TEST_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 1
)
pushd "%~dp0"
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /Fo"test_consume.obj" /Fe"test_consume.exe" test_consume.cpp kernel32.lib
if errorlevel 1 (popd & exit /b 1)
test_consume.exe
set "EU4_CONSUME_TEST_RESULT=!errorlevel!"
popd
exit /b !EU4_CONSUME_TEST_RESULT!
