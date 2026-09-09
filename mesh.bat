@echo off
setlocal

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

.venv\Scripts\python.exe main.py %*
popd