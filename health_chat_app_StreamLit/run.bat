@echo off
setlocal
cd /d "%~dp0"
title Eswatini Health Dashboard

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
    where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    echo Python was not found.
    echo Install it from https://www.python.org and tick "Add python.exe to PATH", then run this file again.
    pause
    exit /b 1
)

%PY% -c "import streamlit, plotly, pandas, pyodbc, requests, openpyxl, docx" >nul 2>nul
if errorlevel 1 (
    echo Installing the required packages, first run only...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Package installation failed. Check your internet connection and try again.
        pause
        exit /b 1
    )
)

echo Starting Eswatini Health Dashboard...
echo Your browser will open automatically. Close this window to stop the app.
echo.
%PY% -m streamlit run app.py

echo.
echo The app has stopped.
pause
