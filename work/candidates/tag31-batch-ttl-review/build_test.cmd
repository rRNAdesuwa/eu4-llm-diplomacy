@echo off
setlocal
set "tag31_ttl_src=%~dp0..\..\..\bridge\native\tag_diplomacy_1375_v31\src\work\candidates\"
set "tag31_ttl_out=%~1"
mkdir "%tag31_ttl_out%" || exit /b 10
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > "%tag31_ttl_out%\environment.stdout" 2>&1
if errorlevel 1 exit /b 11
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tag31_ttl_src%v21-native-pair-guard-r3-1375\native_guard.cpp" /Fo"%tag31_ttl_out%\guard.obj" > "%tag31_ttl_out%\guard.stdout" 2> "%tag31_ttl_out%\guard.stderr"
if errorlevel 1 exit /b 12
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tag31_ttl_src%current-country-tag-cpp-r2-1375\country_resolver.cpp" /Fo"%tag31_ttl_out%\country.obj" > "%tag31_ttl_out%\country.stdout" 2> "%tag31_ttl_out%\country.stderr"
if errorlevel 1 exit /b 13
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tag31_ttl_src%v21-five-cancel-reader-1375\cancel_reader.cpp" /Fo"%tag31_ttl_out%\cancel.obj" > "%tag31_ttl_out%\cancel.stdout" 2> "%tag31_ttl_out%\cancel.stderr"
if errorlevel 1 exit /b 14
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tag31_ttl_src%v24-pair-send-core-r2-1375\pair_send.cpp" /Fo"%tag31_ttl_out%\pair.obj" > "%tag31_ttl_out%\pair.stdout" 2> "%tag31_ttl_out%\pair.stderr"
if errorlevel 1 exit /b 15
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS "%~dp0guard_boundary.cpp" "%tag31_ttl_out%\guard.obj" "%tag31_ttl_out%\country.obj" "%tag31_ttl_out%\cancel.obj" "%tag31_ttl_out%\pair.obj" /Fo"%tag31_ttl_out%\test.obj" /Fe"%tag31_ttl_out%\test.exe" > "%tag31_ttl_out%\test-build.stdout" 2> "%tag31_ttl_out%\test-build.stderr"
if errorlevel 1 exit /b 16
"%tag31_ttl_out%\test.exe" > "%tag31_ttl_out%\test.stdout" 2> "%tag31_ttl_out%\test.stderr"
exit /b %errorlevel%
