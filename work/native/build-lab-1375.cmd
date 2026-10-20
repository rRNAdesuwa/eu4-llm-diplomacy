@echo off
setlocal EnableDelayedExpansion
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "EU4_LAB_VS=%%i"
  call "!EU4_LAB_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 1
)
pushd "%~dp0"
if not exist "..\runtime\native1375-v6" mkdir "..\runtime\native1375-v6"
for /d %%d in ("..\runtime\native1375-v6\session-*") do (
  echo Refusing to rebuild a lab directory containing a process session.
  popd
  exit /b 2
)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\runtime\native1375-v6\research-lab-1375.obj" research-lab-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\runtime\native1375-v6\pair-probe-v6-1375.obj" pair-probe-v6-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\runtime\native1375-v6\pair-preview-v6-1375.obj" pair-preview-v6-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\runtime\native1375-v6\pair-command-v6-1375.obj" pair-command-v6-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\runtime\native1375-v6\pair-engine-1375.obj" pair-engine-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\runtime\native1375-v6\test-controls-1375.obj" test-controls-1375.cpp
if errorlevel 1 (popd & exit /b 1)
ml64 /nologo /c /Fo"..\runtime\native1375-v6\frame.obj" research-frame-v6-1375.asm
if errorlevel 1 (popd & exit /b 1)
link /nologo /DLL /DYNAMICBASE /NXCOMPAT /OUT:"..\runtime\native1375-v6\eu4_pair_lab_1375.dll" "..\runtime\native1375-v6\research-lab-1375.obj" "..\runtime\native1375-v6\pair-probe-v6-1375.obj" "..\runtime\native1375-v6\pair-preview-v6-1375.obj" "..\runtime\native1375-v6\pair-command-v6-1375.obj" "..\runtime\native1375-v6\pair-engine-1375.obj" "..\runtime\native1375-v6\test-controls-1375.obj" "..\runtime\native1375-v6\frame.obj" kernel32.lib user32.lib advapi32.lib
if errorlevel 1 (popd & exit /b 1)
python -B record_lab_build.py
if errorlevel 1 (popd & exit /b 1)
popd
endlocal
