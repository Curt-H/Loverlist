@echo off
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%PYTHON\python.exe"

if not exist "%PY%" (
    echo [ERROR] Python runtime not found: "%PY%"
    exit /b 1
)

"%PY%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Dependencies not installed yet. Run setup.bat first.
    exit /b 1
)

"%PY%" "%ROOT%main.py" %*
endlocal