@echo off
setlocal
set "pair28_src=%~dp0src\work\candidates\v26-gap-curry-bootstrap-1375\"
set "pair28_out=%~1"
mkdir "%pair28_out%" || exit /b 10
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > "%pair28_out%\environment.stdout" 2>&1
if errorlevel 1 exit /b 11
for %%f in (bootstrap installer) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair28_src%%%f.cpp" /Fo"%pair28_out%\%%f.obj" > "%pair28_out%\%%f.stdout" 2> "%pair28_out%\%%f.stderr"
 if errorlevel 1 exit /b 12
)
for %%f in (native_guard native_env) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair28_src%..\v21-native-pair-guard-r3-1375\%%f.cpp" /Fo"%pair28_out%\%%f.obj" > "%pair28_out%\%%f.stdout" 2> "%pair28_out%\%%f.stderr"
 if errorlevel 1 exit /b 13
)
for %%f in (native_pair_engine native_platform submission_guard) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair28_src%..\v24-pair-send-port-r2-1375\%%f.cpp" /Fo"%pair28_out%\%%f.obj" > "%pair28_out%\%%f.stdout" 2> "%pair28_out%\%%f.stderr"
 if errorlevel 1 exit /b 14
)
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair28_src%..\v24-pair-send-core-r2-1375\pair_send.cpp" /Fo"%pair28_out%\pair_component.obj" > "%pair28_out%\pair_component.stdout" 2> "%pair28_out%\pair_component.stderr"
if errorlevel 1 exit /b 15
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair28_src%..\current-country-tag-cpp-r2-1375\country_resolver.cpp" /Fo"%pair28_out%\country.obj" > "%pair28_out%\country.stdout" 2> "%pair28_out%\country.stderr"
if errorlevel 1 exit /b 16
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair28_src%..\v21-five-cancel-reader-1375\cancel_reader.cpp" /Fo"%pair28_out%\cancel.obj" > "%pair28_out%\cancel.stdout" 2> "%pair28_out%\cancel.stderr"
if errorlevel 1 exit /b 17
ml64 /nologo /c /Fo"%pair28_out%\frame.obj" "%pair28_src%frame.asm" > "%pair28_out%\frame.stdout" 2> "%pair28_out%\frame.stderr"
if errorlevel 1 exit /b 18
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS "%pair28_src%test_codec.cpp" "%pair28_out%\pair_component.obj" /Fo"%pair28_out%\test_codec.obj" /Fe"%pair28_out%\test_codec.exe" > "%pair28_out%\test-build.stdout" 2> "%pair28_out%\test-build.stderr"
if errorlevel 1 exit /b 19
"%pair28_out%\test_codec.exe" > "%pair28_out%\test.stdout" 2> "%pair28_out%\test.stderr"
if errorlevel 1 exit /b 20
link /nologo /DLL /MACHINE:X64 /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT /OUT:"%pair28_out%\eu4_pair_send_lab_1375_v28.dll" "%pair28_out%\bootstrap.obj" "%pair28_out%\installer.obj" "%pair28_out%\native_guard.obj" "%pair28_out%\native_env.obj" "%pair28_out%\native_pair_engine.obj" "%pair28_out%\native_platform.obj" "%pair28_out%\submission_guard.obj" "%pair28_out%\pair_component.obj" "%pair28_out%\country.obj" "%pair28_out%\cancel.obj" "%pair28_out%\frame.obj" kernel32.lib user32.lib advapi32.lib bcrypt.lib > "%pair28_out%\link.stdout" 2> "%pair28_out%\link.stderr"
exit /b %errorlevel%
