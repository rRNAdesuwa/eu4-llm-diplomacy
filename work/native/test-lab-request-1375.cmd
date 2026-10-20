@echo off
setlocal EnableDelayedExpansion
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "EU4_LAB_TEST_VS=%%i"
  call "!EU4_LAB_TEST_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 1
)
pushd "%~dp0"
if not exist "..\runtime\native1375-parser-test" mkdir "..\runtime\native1375-parser-test"
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\runtime\native1375-parser-test\pair-engine.obj" pair-engine-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /std:c++17 /EHsc /O2 /W4 /WX /MT /GS /Fo"..\runtime\native1375-parser-test\parser.obj" /Fe"..\runtime\native1375-parser-test\parser.exe" test-lab-request-1375.cpp "..\runtime\native1375-parser-test\pair-engine.obj" kernel32.lib
if errorlevel 1 (popd & exit /b 1)
"..\runtime\native1375-parser-test\parser.exe"
set "EU4_LAB_TEST_RESULT=!errorlevel!"
popd
exit /b !EU4_LAB_TEST_RESULT!
