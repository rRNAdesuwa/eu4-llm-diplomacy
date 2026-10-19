@echo off
setlocal EnableDelayedExpansion
if "%~1"=="" exit /b 2
if exist "%~1" exit /b 3
mkdir "%~1"
if errorlevel 1 exit /b 4
set "EU4_PAIR21_OUT=%~f1"
set "VSCMD_SKIP_SENDTELEMETRY=1"
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "EU4_PAIR21_VS=%%i"
  call "!EU4_PAIR21_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 5
)
pushd "%~dp0"
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc /c pair_component.cpp /Fo"%EU4_PAIR21_OUT%\pair_component.obj" >"%EU4_PAIR21_OUT%\core.stdout" 2>"%EU4_PAIR21_OUT%\core.stderr"
if errorlevel 1 (popd & exit /b 6)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc test_pair_component.cpp "%EU4_PAIR21_OUT%\pair_component.obj" /Fo"%EU4_PAIR21_OUT%\test_pair_component.obj" /Fe"%EU4_PAIR21_OUT%\test_pair_component.exe" /link /INCREMENTAL:NO >"%EU4_PAIR21_OUT%\test-build.stdout" 2>"%EU4_PAIR21_OUT%\test-build.stderr"
if errorlevel 1 (popd & exit /b 7)
"%EU4_PAIR21_OUT%\test_pair_component.exe" >"%EU4_PAIR21_OUT%\test.stdout" 2>"%EU4_PAIR21_OUT%\test.stderr"
set "EU4_PAIR21_RESULT=!errorlevel!"
if not "!EU4_PAIR21_RESULT!"=="0" (popd & exit /b !EU4_PAIR21_RESULT!)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc test_r2_counter.cpp "%EU4_PAIR21_OUT%\pair_component.obj" /Fo"%EU4_PAIR21_OUT%\test_r2_counter.obj" /Fe"%EU4_PAIR21_OUT%\test_r2_counter.exe" /link /INCREMENTAL:NO >"%EU4_PAIR21_OUT%\counter-build.stdout" 2>"%EU4_PAIR21_OUT%\counter-build.stderr"
if errorlevel 1 (popd & exit /b 8)
"%EU4_PAIR21_OUT%\test_r2_counter.exe" >"%EU4_PAIR21_OUT%\counter.stdout" 2>"%EU4_PAIR21_OUT%\counter.stderr"
set "EU4_PAIR21_RESULT=!errorlevel!"
if not "!EU4_PAIR21_RESULT!"=="0" (popd & exit /b !EU4_PAIR21_RESULT!)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc /c adapter\native_pair_engine.cpp /Fo"%EU4_PAIR21_OUT%\adapter.obj" >"%EU4_PAIR21_OUT%\adapter.stdout" 2>"%EU4_PAIR21_OUT%\adapter.stderr"
if errorlevel 1 (popd & exit /b 9)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc test_r3_integration.cpp "%EU4_PAIR21_OUT%\pair_component.obj" "%EU4_PAIR21_OUT%\adapter.obj" /Fo"%EU4_PAIR21_OUT%\r3.obj" /Fe"%EU4_PAIR21_OUT%\r3.exe" /link /INCREMENTAL:NO >"%EU4_PAIR21_OUT%\r3-build.stdout" 2>"%EU4_PAIR21_OUT%\r3-build.stderr"
if errorlevel 1 (popd & exit /b 10)
"%EU4_PAIR21_OUT%\r3.exe" >"%EU4_PAIR21_OUT%\r3.stdout" 2>"%EU4_PAIR21_OUT%\r3.stderr"
set "EU4_PAIR21_RESULT=!errorlevel!"
popd
exit /b !EU4_PAIR21_RESULT!
