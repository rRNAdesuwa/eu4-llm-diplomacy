@echo off
setlocal
set "tagcommand31_src=%~dp0"
set "tagcommand31_out=%~1"
mkdir "%tagcommand31_out%" || exit /b 10
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > "%tagcommand31_out%\environment.stdout" 2>&1
if errorlevel 1 exit /b 11
for %%f in (bootstrap installer) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tagcommand31_src%%%f.cpp" /Fo"%tagcommand31_out%\%%f.obj" > "%tagcommand31_out%\%%f.stdout" 2> "%tagcommand31_out%\%%f.stderr"
 if errorlevel 1 exit /b 12
)
for %%f in (native_guard native_env) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tagcommand31_src%..\v21-native-pair-guard-r3-1375\%%f.cpp" /Fo"%tagcommand31_out%\%%f.obj" > "%tagcommand31_out%\%%f.stdout" 2> "%tagcommand31_out%\%%f.stderr"
 if errorlevel 1 exit /b 13
)
for %%f in (native_pair_engine native_platform submission_guard) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tagcommand31_src%..\v24-pair-send-port-r2-1375\%%f.cpp" /Fo"%tagcommand31_out%\%%f.obj" > "%tagcommand31_out%\%%f.stdout" 2> "%tagcommand31_out%\%%f.stderr"
 if errorlevel 1 exit /b 14
)
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tagcommand31_src%..\v24-pair-send-core-r2-1375\pair_send.cpp" /Fo"%tagcommand31_out%\pair_component.obj" > "%tagcommand31_out%\pair_component.stdout" 2> "%tagcommand31_out%\pair_component.stderr"
if errorlevel 1 exit /b 15
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tagcommand31_src%..\current-country-tag-cpp-r2-1375\country_resolver.cpp" /Fo"%tagcommand31_out%\country.obj" > "%tagcommand31_out%\country.stdout" 2> "%tagcommand31_out%\country.stderr"
if errorlevel 1 exit /b 16
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tagcommand31_src%..\v21-five-cancel-reader-1375\cancel_reader.cpp" /Fo"%tagcommand31_out%\cancel.obj" > "%tagcommand31_out%\cancel.stdout" 2> "%tagcommand31_out%\cancel.stderr"
if errorlevel 1 exit /b 17
ml64 /nologo /c /Fo"%tagcommand31_out%\frame.obj" "%tagcommand31_src%frame.asm" > "%tagcommand31_out%\frame.stdout" 2> "%tagcommand31_out%\frame.stderr"
if errorlevel 1 exit /b 18
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS "%tagcommand31_src%test_codec.cpp" "%tagcommand31_out%\pair_component.obj" /Fo"%tagcommand31_out%\test_codec.obj" /Fe"%tagcommand31_out%\test_codec.exe" > "%tagcommand31_out%\test-build.stdout" 2> "%tagcommand31_out%\test-build.stderr"
if errorlevel 1 exit /b 19
"%tagcommand31_out%\test_codec.exe" > "%tagcommand31_out%\test.stdout" 2> "%tagcommand31_out%\test.stderr"
if errorlevel 1 exit /b 20
link /nologo /DLL /MACHINE:X64 /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT /OUT:"%tagcommand31_out%\eu4_tag_command_1375_v31.dll" "%tagcommand31_out%\bootstrap.obj" "%tagcommand31_out%\installer.obj" "%tagcommand31_out%\native_guard.obj" "%tagcommand31_out%\native_env.obj" "%tagcommand31_out%\native_pair_engine.obj" "%tagcommand31_out%\native_platform.obj" "%tagcommand31_out%\submission_guard.obj" "%tagcommand31_out%\pair_component.obj" "%tagcommand31_out%\country.obj" "%tagcommand31_out%\cancel.obj" "%tagcommand31_out%\frame.obj" kernel32.lib user32.lib advapi32.lib bcrypt.lib > "%tagcommand31_out%\link.stdout" 2> "%tagcommand31_out%\link.stderr"
exit /b %errorlevel%
