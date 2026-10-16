@echo off
setlocal
set "pair24_src=%~dp0"
set "pair24_out=%~1"
mkdir "%pair24_out%" || exit /b 10
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > "%pair24_out%\environment.stdout" 2>&1
if errorlevel 1 exit /b 11
for %%f in (native_pair_engine submission_guard native_platform test_transfer) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair24_src%%%f.cpp" /Fo"%pair24_out%\%%f.obj" > "%pair24_out%\%%f.stdout" 2> "%pair24_out%\%%f.stderr"
 if errorlevel 1 exit /b 12
)
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair24_src%..\v24-pair-send-core-r2-1375\pair_send.cpp" /Fo"%pair24_out%\core.obj" > "%pair24_out%\core.stdout" 2> "%pair24_out%\core.stderr"
if errorlevel 1 exit /b 13
link /nologo /OUT:"%pair24_out%\test_transfer.exe" "%pair24_out%\native_pair_engine.obj" "%pair24_out%\submission_guard.obj" "%pair24_out%\test_transfer.obj" "%pair24_out%\core.obj" > "%pair24_out%\link.stdout" 2> "%pair24_out%\link.stderr"
if errorlevel 1 exit /b 14
"%pair24_out%\test_transfer.exe" > "%pair24_out%\test.stdout" 2> "%pair24_out%\test.stderr"
exit /b %errorlevel%
