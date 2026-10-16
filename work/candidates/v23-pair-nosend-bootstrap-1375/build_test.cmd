@echo off
setlocal
set "pair23_src=%~dp0"
set "pair23_out=%~1"
mkdir "%pair23_out%" || exit /b 10
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > "%pair23_out%\environment.stdout" 2>&1
if errorlevel 1 exit /b 11
for %%f in (bootstrap installer) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair23_src%%%f.cpp" /Fo"%pair23_out%\%%f.obj" > "%pair23_out%\%%f.stdout" 2> "%pair23_out%\%%f.stderr"
 if errorlevel 1 exit /b 12
)
for %%f in (native_guard native_env) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair23_src%..\v21-native-pair-guard-r3-1375\%%f.cpp" /Fo"%pair23_out%\%%f.obj" > "%pair23_out%\%%f.stdout" 2> "%pair23_out%\%%f.stderr"
 if errorlevel 1 exit /b 13
)
for %%f in (native_pair_engine native_platform) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair23_src%..\v21-native-pair-port-r2-1375\%%f.cpp" /Fo"%pair23_out%\%%f.obj" > "%pair23_out%\%%f.stdout" 2> "%pair23_out%\%%f.stderr"
 if errorlevel 1 exit /b 14
)
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair23_src%..\v21-core-pair-nosend-r3-1375\pair_component.cpp" /Fo"%pair23_out%\pair_component.obj" > "%pair23_out%\pair_component.stdout" 2> "%pair23_out%\pair_component.stderr"
if errorlevel 1 exit /b 15
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair23_src%..\current-country-tag-cpp-r2-1375\country_resolver.cpp" /Fo"%pair23_out%\country.obj" > "%pair23_out%\country.stdout" 2> "%pair23_out%\country.stderr"
if errorlevel 1 exit /b 16
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair23_src%..\v21-five-cancel-reader-1375\cancel_reader.cpp" /Fo"%pair23_out%\cancel.obj" > "%pair23_out%\cancel.stdout" 2> "%pair23_out%\cancel.stderr"
if errorlevel 1 exit /b 17
ml64 /nologo /c /Fo"%pair23_out%\frame.obj" "%pair23_src%frame.asm" > "%pair23_out%\frame.stdout" 2> "%pair23_out%\frame.stderr"
if errorlevel 1 exit /b 18
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS "%pair23_src%test_codec.cpp" "%pair23_out%\pair_component.obj" /Fo"%pair23_out%\test_codec.obj" /Fe"%pair23_out%\test_codec.exe" > "%pair23_out%\test-build.stdout" 2> "%pair23_out%\test-build.stderr"
if errorlevel 1 exit /b 19
"%pair23_out%\test_codec.exe" > "%pair23_out%\test.stdout" 2> "%pair23_out%\test.stderr"
if errorlevel 1 exit /b 20
link /nologo /DLL /MACHINE:X64 /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT /OUT:"%pair23_out%\eu4_pair_nosend_lab_1375_v23.dll" "%pair23_out%\bootstrap.obj" "%pair23_out%\installer.obj" "%pair23_out%\native_guard.obj" "%pair23_out%\native_env.obj" "%pair23_out%\native_pair_engine.obj" "%pair23_out%\native_platform.obj" "%pair23_out%\pair_component.obj" "%pair23_out%\country.obj" "%pair23_out%\cancel.obj" "%pair23_out%\frame.obj" kernel32.lib user32.lib advapi32.lib bcrypt.lib > "%pair23_out%\link.stdout" 2> "%pair23_out%\link.stderr"
exit /b %errorlevel%
