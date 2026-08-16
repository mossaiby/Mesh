@echo off
setlocal enabledelayedexpansion

set "PYTHON_BIN="

:: 1. Check Python Launcher 'py -3' (standard on Windows)
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_BIN=py -3"
    goto :found_python
)

:: 2. Check 'python'
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_BIN=python"
    goto :found_python
)

:: 3. Check 'python3'
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_BIN=python3"
    goto :found_python
)

:found_python
if "%PYTHON_BIN%"=="" (
    echo [Error] No compatible Python ^>= 3.10 found in PATH.
    echo Please install Python 3.10 or higher from https://www.python.org/downloads/
    echo (Make sure to check "Add Python to PATH" during installation)
    exit /b 1
)

echo [+] Using Python:
%PYTHON_BIN% --version

:: Check for venv module
%PYTHON_BIN% -c "import venv" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo [Error] The 'venv' module is missing or corrupted in your Python installation.
    echo Please modify/repair your Python installation from the Windows Settings or installer,
    echo and ensure standard library components and pip are selected.
    exit /b 1
)

:: Create .venv if missing
if not exist ".venv\Scripts\python.exe" (
    echo [+] Creating virtual environment in .venv...
    %PYTHON_BIN% -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [Error] Failed to create virtual environment in .venv.
        exit /b 1
    )
) else (
    echo [+] Virtual environment .venv already exists.
)

:: Upgrade pip and install requirements
echo [+] Installing and updating dependencies...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\pip.exe install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [Error] Dependency installation failed.
    exit /b 1
)

echo.
echo [OK] Mesh environment bootstrapped successfully!
echo Start Mesh anytime with: mesh.bat