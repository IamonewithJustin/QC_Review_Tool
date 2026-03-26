@echo off
REM Double-click this file (same folder as AI_QC_Document_Reviewer.exe) to start the app.
cd /d "%~dp0"
if not exist "AI_QC_Document_Reviewer.exe" (
    msg * "AI_QC_Document_Reviewer.exe was not found in this folder."
    exit /b 1
)
start "" "AI_QC_Document_Reviewer.exe"
