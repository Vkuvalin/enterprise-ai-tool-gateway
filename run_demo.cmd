@echo off
setlocal

set "REPO_ROOT=%~dp0"
pushd "%REPO_ROOT%" >nul 2>&1
if errorlevel 1 (
    echo Failed to enter repository root: %REPO_ROOT%
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%scripts\demo\run_demo.ps1"
set "DEMO_EXIT_CODE=%ERRORLEVEL%"

popd >nul 2>&1

if not "%DEMO_EXIT_CODE%"=="0" (
    echo.
    echo Demo runner failed with exit code %DEMO_EXIT_CODE%.
    echo Check the messages above and .runtime\logs for details.
    pause
    exit /b %DEMO_EXIT_CODE%
)

exit /b 0
