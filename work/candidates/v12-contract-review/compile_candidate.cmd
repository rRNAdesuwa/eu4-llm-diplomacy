@echo off
setlocal EnableDelayedExpansion
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "EU4_CONTRACT_VS=%%i"
  call "!EU4_CONTRACT_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 1
)
pushd "%~dp0"
if not exist test-output mkdir test-output
for %%f in (pair-probe-v6-1375 pair-engine-1375 pair-preview-v6-1375 pair-command-v6-1375) do (
  cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"test-output\%%f.obj" "generated\%%f.cpp"
  if errorlevel 1 (popd & exit /b 1)
)
popd
exit /b 0
