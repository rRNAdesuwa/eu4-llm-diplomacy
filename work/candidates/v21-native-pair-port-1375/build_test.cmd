@echo off
setlocal EnableDelayedExpansion
if "%~1"=="" exit /b 2
if exist "%~1" exit /b 3
mkdir "%~1"
if errorlevel 1 exit /b 4
set "PAIRPORT_OUT=%~f1"
set "VSCMD_SKIP_SENDTELEMETRY=1"
if not defined VSINSTALLDIR (
 for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "PAIRPORT_VS=%%i"
 call "!PAIRPORT_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
 if errorlevel 1 exit /b 5
)
pushd "%~dp0"
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc /c component\pair_component.cpp /Fo"%PAIRPORT_OUT%\pair_component.obj" >"%PAIRPORT_OUT%\component.stdout" 2>"%PAIRPORT_OUT%\component.stderr"
if errorlevel 1 (popd & exit /b 6)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc /c native_pair_engine.cpp /Fo"%PAIRPORT_OUT%\native_pair_engine.obj" >"%PAIRPORT_OUT%\adapter.stdout" 2>"%PAIRPORT_OUT%\adapter.stderr"
if errorlevel 1 (popd & exit /b 7)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc /c native_platform.cpp /Fo"%PAIRPORT_OUT%\native_platform.obj" >"%PAIRPORT_OUT%\platform.stdout" 2>"%PAIRPORT_OUT%\platform.stderr"
if errorlevel 1 (popd & exit /b 8)
rem The real platform object is deliberately NOT linked into the fake test.
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc test_native_pair_engine.cpp "%PAIRPORT_OUT%\pair_component.obj" "%PAIRPORT_OUT%\native_pair_engine.obj" /Fo"%PAIRPORT_OUT%\test.obj" /Fe"%PAIRPORT_OUT%\test.exe" /link /INCREMENTAL:NO >"%PAIRPORT_OUT%\test-build.stdout" 2>"%PAIRPORT_OUT%\test-build.stderr"
if errorlevel 1 (popd & exit /b 9)
"%PAIRPORT_OUT%\test.exe" >"%PAIRPORT_OUT%\test.stdout" 2>"%PAIRPORT_OUT%\test.stderr"
set "PAIRPORT_RESULT=!errorlevel!"
if not "!PAIRPORT_RESULT!"=="0" (popd & exit /b !PAIRPORT_RESULT!)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc test_r2_spy_setter.cpp "%PAIRPORT_OUT%\pair_component.obj" "%PAIRPORT_OUT%\native_pair_engine.obj" /Fo"%PAIRPORT_OUT%\r2-setter.obj" /Fe"%PAIRPORT_OUT%\r2-setter.exe" /link /INCREMENTAL:NO >"%PAIRPORT_OUT%\r2-build.stdout" 2>"%PAIRPORT_OUT%\r2-build.stderr"
if errorlevel 1 (popd & exit /b 10)
"%PAIRPORT_OUT%\r2-setter.exe" >"%PAIRPORT_OUT%\r2.stdout" 2>"%PAIRPORT_OUT%\r2.stderr"
set "PAIRPORT_RESULT=!errorlevel!"
popd
exit /b !PAIRPORT_RESULT!
