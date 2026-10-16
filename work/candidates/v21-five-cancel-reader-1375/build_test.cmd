@echo off
setlocal EnableDelayedExpansion
if "%~1"=="" exit /b 2
if exist "%~1" exit /b 3
mkdir "%~1"
if errorlevel 1 exit /b 4
set "CANCEL_TEST_OUT=%~f1"
set "VSCMD_SKIP_SENDTELEMETRY=1"
for /f "usebackq delims=" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "CANCEL_TEST_VS=%%i"
call "%CANCEL_TEST_VS%\VC\Auxiliary\Build\vcvars64.bat" >"%CANCEL_TEST_OUT%\environment.stdout" 2>&1
if errorlevel 1 exit /b 5
pushd "%~dp0"
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc /c ..\v21-core-pair-nosend-r2-1375\pair_component.cpp /Fo"%CANCEL_TEST_OUT%\pair_component.obj" >"%CANCEL_TEST_OUT%\pair.stdout" 2>&1
if errorlevel 1 (popd & exit /b 6)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc /c cancel_reader.cpp /Fo"%CANCEL_TEST_OUT%\cancel_reader.obj" >"%CANCEL_TEST_OUT%\reader.stdout" 2>&1
if errorlevel 1 (popd & exit /b 7)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc test_cancel_reader.cpp "%CANCEL_TEST_OUT%\pair_component.obj" "%CANCEL_TEST_OUT%\cancel_reader.obj" /Fo"%CANCEL_TEST_OUT%\test_cancel_reader.obj" /Fe"%CANCEL_TEST_OUT%\test_cancel_reader.exe" /link /INCREMENTAL:NO >"%CANCEL_TEST_OUT%\test-build.stdout" 2>&1
if errorlevel 1 (popd & exit /b 8)
"%CANCEL_TEST_OUT%\test_cancel_reader.exe" >"%CANCEL_TEST_OUT%\test.stdout" 2>&1
if errorlevel 1 (popd & exit /b 9)
cl /nologo /std:c++17 /O2 /W4 /WX /MT /GS /EHsc test_reader_budget.cpp "%CANCEL_TEST_OUT%\pair_component.obj" /Fo"%CANCEL_TEST_OUT%\test_reader_budget.obj" /Fe"%CANCEL_TEST_OUT%\test_reader_budget.exe" /link /INCREMENTAL:NO >"%CANCEL_TEST_OUT%\budget-build.stdout" 2>&1
if errorlevel 1 (popd & exit /b 10)
"%CANCEL_TEST_OUT%\test_reader_budget.exe" >"%CANCEL_TEST_OUT%\budget.stdout" 2>&1
set "CANCEL_TEST_RESULT=!errorlevel!"
popd
exit /b !CANCEL_TEST_RESULT!
