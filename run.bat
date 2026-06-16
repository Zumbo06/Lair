@echo off
title Lair Launcher
echo Starting Lair...

:: Check if virtual environment exists
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
    python emulator_hub_app.py
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Failed to start Lair from virtual environment.
        pause
    )
    exit /b
)

:: If no venv, advise user
echo [WARNING] No virtual environment found. It is highly recommended to run setup.bat first.
echo Attempting to run with system Python...

:: Try running with python first
python emulator_hub_app.py >nul 2>&1
if %errorlevel% equ 0 exit /b

:: Fallback to python3.11
python3.11 emulator_hub_app.py >nul 2>&1
if %errorlevel% equ 0 exit /b

:: Fallback to python3
python3 emulator_hub_app.py >nul 2>&1
if %errorlevel% equ 0 exit /b

:: If all fail, run visibly to show the traceback
echo Launch failed with quiet fallback. Retrying visibly...
python emulator_hub_app.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start Lair. Please check if Python and PyQt6 are installed.
    echo We recommend running setup.bat to install all dependencies automatically.
    pause
)