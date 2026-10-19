@echo off
setlocal EnableDelayedExpansion
if not defined VSINSTALLDIR (
  for /f "usebackq tokens=*" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -property installationPath`) do set "EU4_RESEARCH_VS=%%i"
  call "!EU4_RESEARCH_VS!\VC\Auxiliary\Build\vcvars64.bat" >nul
  if errorlevel 1 exit /b 1
)
pushd "%~dp0"
if not exist "..\runtime\native1375-v5" mkdir "..\runtime\native1375-v5"
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\runtime\native1375-v5\research-pipeline-1375.obj" research-pipeline-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\runtime\native1375-v5\pair-probe-1375.obj" pair-probe-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\runtime\native1375-v5\pair-preview-1375.obj" pair-preview-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\runtime\native1375-v5\pair-command-1375.obj" pair-command-1375.cpp
if errorlevel 1 (popd & exit /b 1)
cl /nologo /c /std:c++17 /O2 /W4 /WX /MT /GS /Fo"..\runtime\native1375-v5\pair-submit-experiment-1375.obj" pair-submit-experiment-1375.cpp
if errorlevel 1 (popd & exit /b 1)
ml64 /nologo /c /Fo"..\runtime\native1375-v5\frame.obj" research-frame-1375.asm
if errorlevel 1 (popd & exit /b 1)
link /nologo /DLL /DYNAMICBASE /NXCOMPAT /OUT:"..\runtime\native1375-v5\eu4_pair_pipeline_1375.dll" "..\runtime\native1375-v5\research-pipeline-1375.obj" "..\runtime\native1375-v5\pair-probe-1375.obj" "..\runtime\native1375-v5\pair-preview-1375.obj" "..\runtime\native1375-v5\frame.obj" "..\runtime\native1375-v5\pair-command-1375.obj" "..\runtime\native1375-v5\pair-submit-experiment-1375.obj" kernel32.lib user32.lib
if errorlevel 1 (popd & exit /b 1)
python -B record_pipeline_build.py
if errorlevel 1 (popd & exit /b 1)
popd
endlocal
