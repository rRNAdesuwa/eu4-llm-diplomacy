@echo off
setlocal
set "pair24_src=%~dp0"
set "pair24_out=%~1"
mkdir "%pair24_out%" || exit /b 10
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > "%pair24_out%\environment.stdout" 2>&1
if errorlevel 1 exit /b 11
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS "%pair24_src%pair_send.cpp" "%pair24_src%test_send.cpp" /Fo"%pair24_out%\" /Fe"%pair24_out%\test_send.exe" > "%pair24_out%\compile.stdout" 2> "%pair24_out%\compile.stderr"
if errorlevel 1 exit /b 12
"%pair24_out%\test_send.exe" > "%pair24_out%\test.stdout" 2> "%pair24_out%\test.stderr"
exit /b %errorlevel%
