@echo off
setlocal EnableDelayedExpansion
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "EU4_ACTION_TEST_VS=%%i"
  call "!EU4_ACTION_TEST_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 1
)
pushd "%~dp0"
set "EU4_ACTION_OUT=..\..\runtime\native1375-v11-action-extension-test"
if not exist "%EU4_ACTION_OUT%" mkdir "%EU4_ACTION_OUT%"
for %%s in (pair-engine-1375 pair-probe-v6-1375 pair-preview-v6-1375 pair-command-v6-1375) do (
  cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /c /Fo"%EU4_ACTION_OUT%\%%s.obj" "generated\%%s.cpp"
  if errorlevel 1 (popd & exit /b 1)
)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /Fo"%EU4_ACTION_OUT%\test.obj" /Fe"%EU4_ACTION_OUT%\test.exe" test_extension.cpp kernel32.lib
if errorlevel 1 (popd & exit /b 1)
"%EU4_ACTION_OUT%\test.exe"
set "EU4_ACTION_TEST_RESULT=!errorlevel!"
popd
exit /b !EU4_ACTION_TEST_RESULT!
