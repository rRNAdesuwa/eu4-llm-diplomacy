@echo off
setlocal
set "pair24_src=%~dp0"
set "pair24_out=%~1"
mkdir "%pair24_out%" || exit /b 10
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > "%pair24_out%\environment.stdout" 2>&1
if errorlevel 1 exit /b 11
for %%f in (bootstrap installer) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair24_src%%%f.cpp" /Fo"%pair24_out%\%%f.obj" > "%pair24_out%\%%f.stdout" 2> "%pair24_out%\%%f.stderr"
 if errorlevel 1 exit /b 12
)
for %%f in (native_guard native_env) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair24_src%..\v21-native-pair-guard-r3-1375\%%f.cpp" /Fo"%pair24_out%\%%f.obj" > "%pair24_out%\%%f.stdout" 2> "%pair24_out%\%%f.stderr"
 if errorlevel 1 exit /b 13
)
for %%f in (native_pair_engine native_platform submission_guard) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair24_src%..\v24-pair-send-port-1375\%%f.cpp" /Fo"%pair24_out%\%%f.obj" > "%pair24_out%\%%f.stdout" 2> "%pair24_out%\%%f.stderr"
 if errorlevel 1 exit /b 14
)
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair24_src%..\v24-pair-send-core-r2-1375\pair_send.cpp" /Fo"%pair24_out%\pair_component.obj" > "%pair24_out%\pair_component.stdout" 2> "%pair24_out%\pair_component.stderr"
if errorlevel 1 exit /b 15
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair24_src%..\current-country-tag-cpp-r2-1375\country_resolver.cpp" /Fo"%pair24_out%\country.obj" > "%pair24_out%\country.stdout" 2> "%pair24_out%\country.stderr"
if errorlevel 1 exit /b 16
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair24_src%..\v21-five-cancel-reader-1375\cancel_reader.cpp" /Fo"%pair24_out%\cancel.obj" > "%pair24_out%\cancel.stdout" 2> "%pair24_out%\cancel.stderr"
if errorlevel 1 exit /b 17
ml64 /nologo /c /Fo"%pair24_out%\frame.obj" "%pair24_src%frame.asm" > "%pair24_out%\frame.stdout" 2> "%pair24_out%\frame.stderr"
if errorlevel 1 exit /b 18
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS "%pair24_src%test_codec.cpp" "%pair24_out%\pair_component.obj" /Fo"%pair24_out%\test_codec.obj" /Fe"%pair24_out%\test_codec.exe" > "%pair24_out%\test-build.stdout" 2> "%pair24_out%\test-build.stderr"
if errorlevel 1 exit /b 19
"%pair24_out%\test_codec.exe" > "%pair24_out%\test.stdout" 2> "%pair24_out%\test.stderr"
if errorlevel 1 exit /b 20
link /nologo /DLL /MACHINE:X64 /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT /OUT:"%pair24_out%\eu4_pair_send_lab_1375_v24.dll" "%pair24_out%\bootstrap.obj" "%pair24_out%\installer.obj" "%pair24_out%\native_guard.obj" "%pair24_out%\native_env.obj" "%pair24_out%\native_pair_engine.obj" "%pair24_out%\native_platform.obj" "%pair24_out%\submission_guard.obj" "%pair24_out%\pair_component.obj" "%pair24_out%\country.obj" "%pair24_out%\cancel.obj" "%pair24_out%\frame.obj" kernel32.lib user32.lib advapi32.lib bcrypt.lib > "%pair24_out%\link.stdout" 2> "%pair24_out%\link.stderr"
exit /b %errorlevel%
