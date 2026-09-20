@echo off
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%PYTHON\python.exe"

if not exist "%PY%" (
    echo [ERROR] Python runtime not found: "%PY%"
    exit /b 1
)

"%PY%" "%ROOT%run_tests.py" %*
endlocal
