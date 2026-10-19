@echo off
setlocal EnableDelayedExpansion
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "EU4_REVIEW_VS=%%i"
  call "!EU4_REVIEW_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 1
)
pushd "%~dp0"
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /Fo"parser_probe.obj" /Fe"parser_probe.exe" parser_probe.cpp
if errorlevel 1 (popd & exit /b 1)
parser_probe.exe "..\..\runtime\native1375-v10\session-46408-01dd568ed7034bcb\00000000000000000013.request"
set "EU4_REVIEW_RESULT=!errorlevel!"
popd
exit /b !EU4_REVIEW_RESULT!
