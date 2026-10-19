@echo off
setlocal
set "pair27_src=%~dp0"
set "pair27_out=%~1"
mkdir "%pair27_out%" || exit /b 10
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > "%pair27_out%\environment.stdout" 2>&1
if errorlevel 1 exit /b 11
for %%f in (bootstrap installer) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair27_src%%%f.cpp" /Fo"%pair27_out%\%%f.obj" > "%pair27_out%\%%f.stdout" 2> "%pair27_out%\%%f.stderr"
 if errorlevel 1 exit /b 12
)
for %%f in (native_guard native_env) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair27_src%..\v21-native-pair-guard-r3-1375\%%f.cpp" /Fo"%pair27_out%\%%f.obj" > "%pair27_out%\%%f.stdout" 2> "%pair27_out%\%%f.stderr"
 if errorlevel 1 exit /b 13
)
for %%f in (native_pair_engine native_platform submission_guard) do (
 cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair27_src%..\v24-pair-send-port-r2-1375\%%f.cpp" /Fo"%pair27_out%\%%f.obj" > "%pair27_out%\%%f.stdout" 2> "%pair27_out%\%%f.stderr"
 if errorlevel 1 exit /b 14
)
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair27_src%..\v24-pair-send-core-r2-1375\pair_send.cpp" /Fo"%pair27_out%\pair_component.obj" > "%pair27_out%\pair_component.stdout" 2> "%pair27_out%\pair_component.stderr"
if errorlevel 1 exit /b 15
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair27_src%..\current-country-tag-cpp-r2-1375\country_resolver.cpp" /Fo"%pair27_out%\country.obj" > "%pair27_out%\country.stdout" 2> "%pair27_out%\country.stderr"
if errorlevel 1 exit /b 16
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS /c "%pair27_src%..\v21-five-cancel-reader-1375\cancel_reader.cpp" /Fo"%pair27_out%\cancel.obj" > "%pair27_out%\cancel.stdout" 2> "%pair27_out%\cancel.stderr"
if errorlevel 1 exit /b 17
ml64 /nologo /c /Fo"%pair27_out%\frame.obj" "%pair27_src%frame.asm" > "%pair27_out%\frame.stdout" 2> "%pair27_out%\frame.stderr"
if errorlevel 1 exit /b 18
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 /MT /GS "%pair27_src%test_codec.cpp" "%pair27_out%\pair_component.obj" /Fo"%pair27_out%\test_codec.obj" /Fe"%pair27_out%\test_codec.exe" > "%pair27_out%\test-build.stdout" 2> "%pair27_out%\test-build.stderr"
if errorlevel 1 exit /b 19
"%pair27_out%\test_codec.exe" > "%pair27_out%\test.stdout" 2> "%pair27_out%\test.stderr"
if errorlevel 1 exit /b 20
link /nologo /DLL /MACHINE:X64 /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT /OUT:"%pair27_out%\eu4_pair_send_lab_1375_v27.dll" "%pair27_out%\bootstrap.obj" "%pair27_out%\installer.obj" "%pair27_out%\native_guard.obj" "%pair27_out%\native_env.obj" "%pair27_out%\native_pair_engine.obj" "%pair27_out%\native_platform.obj" "%pair27_out%\submission_guard.obj" "%pair27_out%\pair_component.obj" "%pair27_out%\country.obj" "%pair27_out%\cancel.obj" "%pair27_out%\frame.obj" kernel32.lib user32.lib advapi32.lib bcrypt.lib > "%pair27_out%\link.stdout" 2> "%pair27_out%\link.stderr"
exit /b %errorlevel%
