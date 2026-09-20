@echo off
setlocal
REM ============================================================
REM  Loverlist one-click environment setup
REM  Runtime : embedded Python 3.11.9 (the PYTHON folder).
REM  If PYTHON is missing, download the "Windows embeddable
REM  package (64-bit)" for 3.11.9 from python.org and extract
REM  it into .\PYTHON
REM ============================================================
set "ROOT=%~dp0"
set "PY=%ROOT%PYTHON\python.exe"

if not exist "%PY%" (
    echo [ERROR] Python runtime not found: "%PY%"
    exit /b 1
)

echo [1/3] Ensuring "import site" is enabled in python311._pth ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%ROOT%PYTHON\python311._pth'; (Get-Content $p) -replace '^#import site','import site' | Set-Content $p -Encoding ASCII"

echo [2/3] Bootstrapping pip if missing ...
"%PY%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo        Downloading get-pip.py ...
    curl.exe -L -o "%TEMP%\get-pip.py" https://bootstrap.pypa.io/get-pip.py || exit /b 1
    "%PY%" "%TEMP%\get-pip.py" --no-warn-script-location || exit /b 1
) else (
    echo        pip already present, skip.
)

echo [3/3] Installing dependencies from requirements.txt ...
"%PY%" -m pip install -r "%ROOT%requirements.txt" || exit /b 1

echo.
echo Setup done. Run run.bat to start Loverlist.
endlocal