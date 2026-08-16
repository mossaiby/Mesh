@echo off
setlocal

:: Auto-bootstrap if virtual environment is not yet created
if not exist ".venv\Scripts\python.exe" (
    echo [!] Virtual environment not found (.venv\Scripts\python.exe^).
    echo [+] Running bootstrap.bat to initialize environment...
    call bootstrap.bat
    if %ERRORLEVEL% neq 0 (
        echo [Error] Failed to bootstrap environment.
        exit /b 1
    )
)

.venv\Scripts\python.exe main.py %*