@echo off
setlocal EnableExtensions
title Build portable AI QC Document Reviewer
cd /d "%~dp0"

REM Optional: copy proxy_local.bat.example to proxy_local.bat and set HTTP_PROXY / HTTPS_PROXY
if exist "proxy_local.bat" (
    call "proxy_local.bat"
)

REM pip defaults to a 15s read timeout; slow proxies often need much longer
set "PIP_DEFAULT_TIMEOUT=300"

echo.
echo ========================================
echo   Build portable app (PyInstaller)
echo ========================================
echo.
if defined HTTP_PROXY echo HTTP_PROXY is set for this session.
if defined HTTPS_PROXY echo HTTPS_PROXY is set for this session.
echo pip timeout: %PIP_DEFAULT_TIMEOUT%s ^(slow downloads via firewall^)
echo.

set "PIP_OPTS=--default-timeout=300 --retries 10"

REM Prefer Python launcher, then python on PATH
set "PYEXE="
where py >nul 2>&1 && set "PYEXE=py -3"
if not defined PYEXE where python >nul 2>&1 && set "PYEXE=python"
if not defined PYEXE (
    echo ERROR: Python was not found. Install Python 3.10+ from python.org and try again.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment .venv ...
    %PYEXE% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create .venv
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Could not activate .venv
    pause
    exit /b 1
)

echo Upgrading pip ...
python -m pip install %PIP_OPTS% --upgrade pip
if errorlevel 1 goto :fail

echo Installing dependencies ...
python -m pip install %PIP_OPTS% -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :fail

echo Running PyInstaller ...
pyinstaller ai_qc_reviewer.spec --clean
if errorlevel 1 goto :fail

echo.
echo Build finished. Output folder:
echo   %cd%\dist\AI_QC_Document_Reviewer\
echo.
echo You can zip that folder for end users. They double-click:
echo   AI_QC_Document_Reviewer.exe   or   Start AI QC Reviewer.bat
echo.

if exist "dist\AI_QC_Document_Reviewer" (
    explorer "dist\AI_QC_Document_Reviewer"
)

pause
exit /b 0

:fail
echo.
echo Build failed. See messages above.
pause
exit /b 1
