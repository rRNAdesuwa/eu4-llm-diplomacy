@echo off
if not "%EU4_V15_ROOT_REVIEW_APPROVED%"=="1" (
  echo v15 formal build requires root source-set and host review.
  exit /b 90
)
setlocal EnableDelayedExpansion
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "EU4_LAB_VS=%%i"
  call "!EU4_LAB_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 1
)
pushd "%~dp0"
if exist "..\..\runtime\native1375-v15\build.json" (popd & exit /b 91)
if exist "..\..\runtime\native1375-v15\eu4_pair_lab_v15_1375.dll" (popd & exit /b 92)
if not exist "..\..\runtime\native1375-v15" mkdir "..\..\runtime\native1375-v15"
for /d %%d in ("..\..\runtime\native1375-v15\session-*") do (
  echo Refusing to rebuild a lab directory containing a process session.
  popd
  exit /b 2
)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\..\runtime\native1375-v15\research-lab-1375.obj" research-lab-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /EHsc /O2 /W4 /WX /MT /GS /Fo"..\..\runtime\native1375-v15\peace-owned-lifecycle-1375.obj" peace-owned-lifecycle-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\..\runtime\native1375-v15\pair-probe-v6-1375.obj" pair-probe-v6-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\..\runtime\native1375-v15\pair-preview-v6-1375.obj" pair-preview-v6-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\..\runtime\native1375-v15\pair-command-v6-1375.obj" pair-command-v6-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\..\runtime\native1375-v15\pair-engine-1375.obj" pair-engine-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\..\runtime\native1375-v15\test-controls-1375.obj" test-controls-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\..\runtime\native1375-v15\test-fixture-v15-1375.obj" ..\test-fixture-v15-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\..\runtime\native1375-v15\test-acceptance-1375.obj" test-acceptance-1375.cpp
if errorlevel 1 (popd & exit /b 1)
ml64 /nologo /c /Fo"..\..\runtime\native1375-v15\frame.obj" research-frame-v6-1375.asm
if errorlevel 1 (popd & exit /b 1)
link /nologo /DLL /DYNAMICBASE /NXCOMPAT /OUT:"..\..\runtime\native1375-v15\eu4_pair_lab_v15_1375.dll" "..\..\runtime\native1375-v15\research-lab-1375.obj" "..\..\runtime\native1375-v15\pair-probe-v6-1375.obj" "..\..\runtime\native1375-v15\pair-preview-v6-1375.obj" "..\..\runtime\native1375-v15\pair-command-v6-1375.obj" "..\..\runtime\native1375-v15\pair-engine-1375.obj" "..\..\runtime\native1375-v15\test-controls-1375.obj" "..\..\runtime\native1375-v15\frame.obj" "..\..\runtime\native1375-v15\test-fixture-v15-1375.obj" "..\..\runtime\native1375-v15\peace-owned-lifecycle-1375.obj" "..\..\runtime\native1375-v15\test-acceptance-1375.obj" kernel32.lib user32.lib advapi32.lib
if errorlevel 1 (popd & exit /b 1)
python -B ..\record_lab_v15_build.py
if errorlevel 1 (popd & exit /b 1)
popd
endlocal
