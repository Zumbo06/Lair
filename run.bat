@echo off
title EmulatorHub Launcher
echo Starting EmulatorHub...

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
    echo [ERROR] Failed to start EmulatorHub. Please check if Python and PyQt6 are installed.
    pause
)