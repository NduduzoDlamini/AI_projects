
@echo off
cd /d "G:\VannaWorkspace"

echo Starting Local AI Health Data Analyst...
"G:\VannaWorkspace\.venv\Scripts\python.exe" app.py

if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)

