@echo off
setlocal enabledelayedexpansion
REM DirigentAI Installer for Windows CMD
REM This batch file detects available install methods and runs the appropriate one.

echo.
echo ========================================
echo   DirigentAI Installer for Windows
echo ========================================
echo.

REM Check for Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH.
    echo Please install Python 3.11+
    echo.
    echo You can install Python using one of these methods:
    echo   1. Microsoft Store: Search for "Python 3.11" or newer
    echo   2. Official website: https://python.org/downloads/windows/
    echo   3. Winget: winget install Python.Python.3.11
    echo   4. Chocolatey: choco install python311
    echo   5. Scoop: scoop install python311
    echo.
    echo After installing Python, run this installer again.
    echo.
    pause
    exit /b 1
)

REM Check Python version
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Cannot determine Python version.
    echo.
    pause
    exit /b 1
)

REM Try to parse Python version (simple check)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [INFO] Found Python %PYTHON_VERSION%

REM Check if Python version is 3.11 or higher
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set PYTHON_MAJOR=%%a
    set PYTHON_MINOR=%%b
)

if !PYTHON_MAJOR! LSS 3 (
    echo [ERROR] Python 3.11+ required, but found %PYTHON_VERSION%
    echo Please upgrade Python to version 3.11 or newer.
    echo.
    echo Upgrade methods:
    echo   1. Microsoft Store: Search for "Python 3.11" or newer
    echo   2. Official website: https://python.org/downloads/windows/
    echo   3. Winget: winget install --upgrade Python.Python.3.11
    echo   4. Chocolatey: choco install python311
    echo   5. Scoop: scoop install python311
    echo.
    pause
    exit /b 1
)

if !PYTHON_MAJOR! EQU 3 if !PYTHON_MINOR! LSS 11 (
    echo [ERROR] Python 3.11+ required, but found %PYTHON_VERSION%
    echo Please upgrade Python to version 3.11 or newer.
    echo.
    echo Upgrade methods:
    echo   1. Microsoft Store: Search for "Python 3.11" or newer
    echo   2. Official website: https://python.org/downloads/windows/
    echo   3. Winget: winget install --upgrade Python.Python.3.11
    echo   4. Chocolatey: choco install python311
    echo   5. Scoop: scoop install python311
    echo.
    pause
    exit /b 1
)

REM Check if PowerShell is available
where powershell >nul 2>nul
if %errorlevel% equ 0 (
    echo [INFO] Using PowerShell installer...
    echo.
    powershell -ExecutionPolicy Bypass -NoProfile -File "install.ps1"
    if %errorlevel% equ 0 (
        exit /b 0
    ) else (
        echo [WARNING] PowerShell installer failed, trying Python installer...
        echo.
    )
)

REM Try Python universal installer
echo [INFO] Using Python universal installer...
echo.
python install.py
if %errorlevel% neq 0 (
    echo [ERROR] Installation failed.
    echo.
    echo Please try manual installation:
    echo 1. Create virtual environment: python -m venv venv
    echo 2. Activate: venv\Scripts\activate
    echo 3. Install dependencies: pip install -r requirements.txt
    echo 4. Install Playwright: python -m playwright install chromium
    echo 5. Run setup: python main.py setup
    echo.
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Installation complete!
echo.
echo To start DirigentAI:
echo   1. venv\Scripts\activate
echo   2. python main.py cli
echo.
pause