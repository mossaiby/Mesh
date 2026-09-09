@echo off
setlocal

:: Capture the caller's current directory before we change into Mesh's own
:: directory below, so main.py can be told where the user actually invoked
:: mesh.bat from (this lets mesh.bat be called from anywhere, not just its own dir).
set "CALLER_DIR=%CD%"

:: Resolve the script directory and change to it
pushd %~dp0

:: Ensure Python uses UTF-8 encoding for stdin/stdout
set PYTHONIOENCODING=utf-8

:: Auto-bootstrap if virtual environment is not yet created
if not exist ".venv\Scripts\python.exe" (
    echo [!] Virtual environment not found (.venv\Scripts\python.exe^).
    echo [+] Running bootstrap.bat to initialize environment...
    call bootstrap.bat
    if %ERRORLEVEL% neq 0 (
        echo [Error] Failed to bootstrap environment.
        popd
        exit /b 1
    )
)

.venv\Scripts\python.exe main.py --cwd "%CALLER_DIR%" %*
popd
