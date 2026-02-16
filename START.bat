@echo off
title Electrical Estimator
echo.
echo  ============================================
echo   Electrical Estimator - Starting Up...
echo  ============================================
echo.

:: Check for Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python is not installed or not in PATH.
    echo  Download it from https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

:: Show Python version
echo  Found Python:
python --version
echo.

:: Install dependencies if needed (only runs once, fast after that)
echo  Checking dependencies...
pip install -r "%~dp0requirements.txt" --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo  [ERROR] Failed to install dependencies.
    echo  Try running: pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
echo  All dependencies OK.
echo.

:: Start the app
echo  Starting server at http://localhost:5000
echo  Press Ctrl+C to stop.
echo.
echo  ============================================
echo   Opening browser...
echo  ============================================
echo.

:: Open browser after a short delay
start "" "http://localhost:5000"

:: Run Flask
python "%~dp0app.py"

pause
