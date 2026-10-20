@echo off
setlocal
set "source_dir=%~dp0"
set "build_dir=%~1"
mkdir "%build_dir%" || exit /b 10
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" > "%build_dir%\environment.stdout" 2>&1
if errorlevel 1 exit /b 11
cl /nologo /std:c++17 /EHsc /W4 /WX /Od /c "%source_dir%country_resolver.cpp" /Fo"%build_dir%\country_resolver.obj" > "%build_dir%\core.stdout" 2> "%build_dir%\core.stderr"
if errorlevel 1 exit /b 12
cl /nologo /std:c++17 /EHsc /W4 /WX /Od "%source_dir%test_country_resolver.cpp" "%build_dir%\country_resolver.obj" /Fo"%build_dir%\test_country_resolver.obj" /Fe"%build_dir%\test_country_resolver.exe" > "%build_dir%\test-build.stdout" 2> "%build_dir%\test-build.stderr"
if errorlevel 1 exit /b 13
"%build_dir%\test_country_resolver.exe" > "%build_dir%\test.stdout" 2> "%build_dir%\test.stderr"
exit /b %errorlevel%
