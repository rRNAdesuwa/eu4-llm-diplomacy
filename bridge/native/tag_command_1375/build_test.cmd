@echo off
setlocal
set "tagcommand30_src=%~dp0src\work\candidates\v26-gap-curry-bootstrap-1375\"
set "tagcommand30_out=%~1"
mkdir "%tagcommand30_out%" || exit /b 10
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > "%tagcommand30_out%\environment.stdout" 2>&1
if errorlevel 1 exit /b 11
for %%f in (bootstrap installer) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tagcommand30_src%%%f.cpp" /Fo"%tagcommand30_out%\%%f.obj" > "%tagcommand30_out%\%%f.stdout" 2> "%tagcommand30_out%\%%f.stderr"
 if errorlevel 1 exit /b 12
)
for %%f in (native_guard native_env) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tagcommand30_src%..\v21-native-pair-guard-r3-1375\%%f.cpp" /Fo"%tagcommand30_out%\%%f.obj" > "%tagcommand30_out%\%%f.stdout" 2> "%tagcommand30_out%\%%f.stderr"
 if errorlevel 1 exit /b 13
)
for %%f in (native_pair_engine native_platform submission_guard) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tagcommand30_src%..\v24-pair-send-port-r2-1375\%%f.cpp" /Fo"%tagcommand30_out%\%%f.obj" > "%tagcommand30_out%\%%f.stdout" 2> "%tagcommand30_out%\%%f.stderr"
 if errorlevel 1 exit /b 14
)
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tagcommand30_src%..\v24-pair-send-core-r2-1375\pair_send.cpp" /Fo"%tagcommand30_out%\pair_component.obj" > "%tagcommand30_out%\pair_component.stdout" 2> "%tagcommand30_out%\pair_component.stderr"
if errorlevel 1 exit /b 15
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tagcommand30_src%..\current-country-tag-cpp-r2-1375\country_resolver.cpp" /Fo"%tagcommand30_out%\country.obj" > "%tagcommand30_out%\country.stdout" 2> "%tagcommand30_out%\country.stderr"
if errorlevel 1 exit /b 16
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%tagcommand30_src%..\v21-five-cancel-reader-1375\cancel_reader.cpp" /Fo"%tagcommand30_out%\cancel.obj" > "%tagcommand30_out%\cancel.stdout" 2> "%tagcommand30_out%\cancel.stderr"
if errorlevel 1 exit /b 17
ml64 /nologo /c /Fo"%tagcommand30_out%\frame.obj" "%tagcommand30_src%frame.asm" > "%tagcommand30_out%\frame.stdout" 2> "%tagcommand30_out%\frame.stderr"
if errorlevel 1 exit /b 18
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS "%tagcommand30_src%test_codec.cpp" "%tagcommand30_out%\pair_component.obj" /Fo"%tagcommand30_out%\test_codec.obj" /Fe"%tagcommand30_out%\test_codec.exe" > "%tagcommand30_out%\test-build.stdout" 2> "%tagcommand30_out%\test-build.stderr"
if errorlevel 1 exit /b 19
"%tagcommand30_out%\test_codec.exe" > "%tagcommand30_out%\test.stdout" 2> "%tagcommand30_out%\test.stderr"
if errorlevel 1 exit /b 20
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS "%tagcommand30_src%test_actor_guard.cpp" "%tagcommand30_out%\pair_component.obj" "%tagcommand30_out%\native_guard.obj" "%tagcommand30_out%\country.obj" "%tagcommand30_out%\cancel.obj" /Fo"%tagcommand30_out%\test_actor_guard.obj" /Fe"%tagcommand30_out%\test_actor_guard.exe" > "%tagcommand30_out%\actor-test-build.stdout" 2> "%tagcommand30_out%\actor-test-build.stderr"
if errorlevel 1 exit /b 21
"%tagcommand30_out%\test_actor_guard.exe" >> "%tagcommand30_out%\test.stdout" 2>> "%tagcommand30_out%\test.stderr"
if errorlevel 1 exit /b 22
link /nologo /DLL /MACHINE:X64 /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT /OUT:"%tagcommand30_out%\eu4_tag_command_1375_v30.dll" "%tagcommand30_out%\bootstrap.obj" "%tagcommand30_out%\installer.obj" "%tagcommand30_out%\native_guard.obj" "%tagcommand30_out%\native_env.obj" "%tagcommand30_out%\native_pair_engine.obj" "%tagcommand30_out%\native_platform.obj" "%tagcommand30_out%\submission_guard.obj" "%tagcommand30_out%\pair_component.obj" "%tagcommand30_out%\country.obj" "%tagcommand30_out%\cancel.obj" "%tagcommand30_out%\frame.obj" kernel32.lib user32.lib advapi32.lib bcrypt.lib > "%tagcommand30_out%\link.stdout" 2> "%tagcommand30_out%\link.stderr"
exit /b %errorlevel%
