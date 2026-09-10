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

:: Auto-bootstrap if the virtual environment is missing or incomplete (e.g. a
:: previous bootstrap run failed partway through and left python.exe behind
:: without pip - checking for pip.exe here, not just python.exe, makes sure
:: that gets repaired automatically instead of silently reused).
if not exist ".venv\Scripts\pip.exe" (
    echo [!] Virtual environment not found or incomplete (.venv\Scripts\pip.exe^).
    echo [+] Running bootstrap.bat to initialize environment...
    call bootstrap.bat
    if %ERRORLEVEL% neq 0 (
        echo [Error] Failed to bootstrap environment.
        popd
        exit /b 1
    )
)

:: Restore caller directory first
popd

:: Exit batch mode into command-line context before executing Python
endlocal & set "PYTHONIOENCODING=utf-8" & goto #_undefined_# 2>nul || title %COMSPEC% & "%~dp0.venv\Scripts\python.exe" "%~dp0main.py" --cwd "%CALLER_DIR%" %*
