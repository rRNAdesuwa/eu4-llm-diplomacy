@echo off
setlocal
set "pair22_src=%~dp0"
set "pair22_out=%~1"
mkdir "%pair22_out%" || exit /b 10
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > "%pair22_out%\environment.stdout" 2>&1
if errorlevel 1 exit /b 11
for %%f in (bootstrap installer) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair22_src%%%f.cpp" /Fo"%pair22_out%\%%f.obj" > "%pair22_out%\%%f.stdout" 2> "%pair22_out%\%%f.stderr"
 if errorlevel 1 exit /b 12
)
for %%f in (native_guard native_env) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair22_src%..\v21-native-pair-guard-r2-1375\%%f.cpp" /Fo"%pair22_out%\%%f.obj" > "%pair22_out%\%%f.stdout" 2> "%pair22_out%\%%f.stderr"
 if errorlevel 1 exit /b 13
)
for %%f in (native_pair_engine native_platform) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair22_src%..\v21-native-pair-port-r2-1375\%%f.cpp" /Fo"%pair22_out%\%%f.obj" > "%pair22_out%\%%f.stdout" 2> "%pair22_out%\%%f.stderr"
 if errorlevel 1 exit /b 14
)
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair22_src%..\v21-core-pair-nosend-r3-1375\pair_component.cpp" /Fo"%pair22_out%\pair_component.obj" > "%pair22_out%\pair_component.stdout" 2> "%pair22_out%\pair_component.stderr"
if errorlevel 1 exit /b 15
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair22_src%..\current-country-tag-cpp-1375\country_resolver.cpp" /Fo"%pair22_out%\country.obj" > "%pair22_out%\country.stdout" 2> "%pair22_out%\country.stderr"
if errorlevel 1 exit /b 16
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair22_src%..\v21-five-cancel-reader-1375\cancel_reader.cpp" /Fo"%pair22_out%\cancel.obj" > "%pair22_out%\cancel.stdout" 2> "%pair22_out%\cancel.stderr"
if errorlevel 1 exit /b 17
ml64 /nologo /c /Fo"%pair22_out%\frame.obj" "%pair22_src%frame.asm" > "%pair22_out%\frame.stdout" 2> "%pair22_out%\frame.stderr"
if errorlevel 1 exit /b 18
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS "%pair22_src%test_codec.cpp" "%pair22_out%\pair_component.obj" /Fo"%pair22_out%\test_codec.obj" /Fe"%pair22_out%\test_codec.exe" > "%pair22_out%\test-build.stdout" 2> "%pair22_out%\test-build.stderr"
if errorlevel 1 exit /b 19
"%pair22_out%\test_codec.exe" > "%pair22_out%\test.stdout" 2> "%pair22_out%\test.stderr"
if errorlevel 1 exit /b 20
link /nologo /DLL /MACHINE:X64 /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT /OUT:"%pair22_out%\eu4_pair_nosend_lab_1375_v22.dll" "%pair22_out%\bootstrap.obj" "%pair22_out%\installer.obj" "%pair22_out%\native_guard.obj" "%pair22_out%\native_env.obj" "%pair22_out%\native_pair_engine.obj" "%pair22_out%\native_platform.obj" "%pair22_out%\pair_component.obj" "%pair22_out%\country.obj" "%pair22_out%\cancel.obj" "%pair22_out%\frame.obj" kernel32.lib user32.lib advapi32.lib bcrypt.lib > "%pair22_out%\link.stdout" 2> "%pair22_out%\link.stderr"
exit /b %errorlevel%
