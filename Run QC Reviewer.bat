@echo off
title AI QC Document Reviewer
cd /d "%~dp0"

REM Prefer project venv (after running Build portable app.bat or manual venv)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
    goto :check
)
where py >nul 2>&1 && (
    py -3 main.py
    goto :check
)
python main.py

:check
if errorlevel 1 (
    echo.
    echo The program exited with an error. Install Python 3.10+ and double-click
    echo   Build portable app.bat
    echo to create the environment and dependencies, or run from source after:
    echo   python -m venv .venv
    echo.
    pause
)
