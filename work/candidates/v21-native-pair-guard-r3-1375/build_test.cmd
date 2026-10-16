@echo off
setlocal
set "guard_src=%~dp0"
set "guard_out=%~1"
mkdir "%guard_out%" || exit /b 10
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > "%guard_out%\environment.stdout" 2>&1
if errorlevel 1 exit /b 11
cl /nologo /std:c++17 /EHsc /W4 /WX /Od /c "%guard_src%environment_binding.cpp" /Fo"%guard_out%\environment_binding.obj" > "%guard_out%\binding.stdout" 2> "%guard_out%\binding.stderr"
if errorlevel 1 exit /b 17
cl /nologo /std:c++17 /EHsc /W4 /WX /Od /c "%guard_src%native_env.cpp" /Fo"%guard_out%\native_env.obj" > "%guard_out%\native_env.stdout" 2> "%guard_out%\native_env.stderr"
if errorlevel 1 exit /b 18
cl /nologo /std:c++17 /EHsc /W4 /WX /Od /c "%guard_src%native_guard.cpp" /Fo"%guard_out%\native_guard.obj" > "%guard_out%\guard.stdout" 2> "%guard_out%\guard.stderr"
if errorlevel 1 exit /b 12
cl /nologo /std:c++17 /EHsc /W4 /WX /Od /c "%guard_src%..\current-country-tag-cpp-r2-1375\country_resolver.cpp" /Fo"%guard_out%\country.obj" > "%guard_out%\country.stdout" 2> "%guard_out%\country.stderr"
if errorlevel 1 exit /b 13
cl /nologo /std:c++17 /EHsc /W4 /WX /Od /c "%guard_src%..\v21-five-cancel-reader-1375\cancel_reader.cpp" /Fo"%guard_out%\cancel.obj" > "%guard_out%\cancel.stdout" 2> "%guard_out%\cancel.stderr"
if errorlevel 1 exit /b 14
cl /nologo /std:c++17 /EHsc /W4 /WX /Od /c "%guard_src%..\v21-core-pair-nosend-r3-1375\pair_component.cpp" /Fo"%guard_out%\pair.obj" > "%guard_out%\pair.stdout" 2> "%guard_out%\pair.stderr"
if errorlevel 1 exit /b 15
cl /nologo /std:c++17 /EHsc /W4 /WX /Od /c "%guard_src%..\v21-native-pair-port-r2-1375\native_pair_engine.cpp" /Fo"%guard_out%\adapter.obj" > "%guard_out%\adapter.stdout" 2> "%guard_out%\adapter.stderr"
if errorlevel 1 exit /b 19
cl /nologo /std:c++17 /EHsc /W4 /WX /Od "%guard_src%test_native_guard.cpp" "%guard_out%\native_guard.obj" "%guard_out%\country.obj" "%guard_out%\cancel.obj" "%guard_out%\pair.obj" "%guard_out%\adapter.obj" /Fo"%guard_out%\test_native_guard.obj" /Fe"%guard_out%\test_native_guard.exe" > "%guard_out%\test-build.stdout" 2> "%guard_out%\test-build.stderr"
if errorlevel 1 exit /b 16
rem The actual Environment binding object is not linked into the fake executable.
"%guard_out%\test_native_guard.exe" > "%guard_out%\test.stdout" 2> "%guard_out%\test.stderr"
if errorlevel 1 exit /b 20
cl /nologo /std:c++17 /EHsc /W4 /WX /Od "%guard_src%test_native_env_types.cpp" "%guard_out%\native_env.obj" /Fo"%guard_out%\test_env.obj" /Fe"%guard_out%\test_env.exe" /link bcrypt.lib user32.lib > "%guard_out%\test-env-build.stdout" 2> "%guard_out%\test-env-build.stderr"
if errorlevel 1 exit /b 21
"%guard_out%\test_env.exe" > "%guard_out%\test-env.stdout" 2> "%guard_out%\test-env.stderr"
exit /b %errorlevel%
