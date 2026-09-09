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

:: Check for ensurepip. On Windows this is normally bundled by the python.org
:: installer, but some stripped-down or corporate Python installs omit it -
:: that lets venv creation "succeed" while leaving pip missing inside it, so
:: we check for it explicitly with a clear message rather than failing later
:: with a confusing "pip not found" error.
%PYTHON_BIN% -c "import ensurepip" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo [Error] The 'ensurepip' component is missing, so a virtual environment can be
    echo created but won't have pip installed inside it.
    echo Please modify/repair your Python installation from the Windows Settings or installer,
    echo and ensure pip is selected as a feature.
    exit /b 1
)

:: Create (or repair) the virtual environment. We check for pip.exe rather
:: than just python.exe: if a previous bootstrap attempt failed partway
:: through, it can leave python.exe behind without pip ever being installed.
:: Checking python.exe alone would silently reuse that broken environment on
:: every subsequent run instead of repairing it, and Mesh would then fail
:: later with a confusing "ModuleNotFoundError" unrelated to the real cause.
if exist ".venv\Scripts\pip.exe" (
    echo [+] Virtual environment .venv already exists.
) else (
    if exist ".venv" (
        echo [!] Found an incomplete .venv - pip is missing, recreating it...
        rmdir /s /q ".venv"
    )
    echo [+] Creating virtual environment in .venv...
    %PYTHON_BIN% -m venv .venv
    if %ERRORLEVEL% neq 0 (
        rmdir /s /q ".venv" >nul 2>&1
        echo [Error] Failed to create virtual environment in .venv.
        exit /b 1
    )
    if not exist ".venv\Scripts\pip.exe" (
        rmdir /s /q ".venv" >nul 2>&1
        echo.
        echo [Error] Virtual environment was created but pip is missing.
        echo Please ensure pip/ensurepip is installed for your Python and try again.
        exit /b 1
    )
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
