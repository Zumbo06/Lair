@echo off
title EmulatorHub Setup
echo Starting EmulatorHub Setup...

:: Check for python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ and ensure it's added to your PATH.
    pause
    exit /b
)

:: Create Virtual Environment
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b
    )
) else (
    echo Virtual environment already exists.
)

:: Activate Virtual Environment and install requirements
echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Upgrading pip...
python -m pip install --upgrade pip

echo Installing requirements...
if exist "Requirements.txt" (
    pip install -r Requirements.txt
) else (
    echo [WARNING] Requirements.txt not found. Skipping dependency installation.
)

:: Create Desktop Shortcut
echo.
set /p create_shortcut="Do you want to create a desktop shortcut? (Y/N): "
if /i "%create_shortcut%"=="Y" (
    echo Creating desktop shortcut...
    set SCRIPT="%TEMP%\CreateShortcut.vbs"
    echo Set oWS = WScript.CreateObject("WScript.Shell") > %SCRIPT%
    echo sLinkFile = "%USERPROFILE%\Desktop\EmulatorHub.lnk" >> %SCRIPT%
    echo Set oLink = oWS.CreateShortcut(sLinkFile) >> %SCRIPT%
    echo oLink.TargetPath = "%~dp0run.bat" >> %SCRIPT%
    echo oLink.WorkingDirectory = "%~dp0" >> %SCRIPT%
    echo oLink.IconLocation = "%~dp0icons\Gamepad.png" >> %SCRIPT%
    echo oLink.Description = "Launch EmulatorHub" >> %SCRIPT%
    echo oLink.Save >> %SCRIPT%
    cscript /nologo %SCRIPT%
    del %SCRIPT%
    echo Shortcut created on Desktop.
)

echo.
echo Setup Complete! You can now run the application using run.bat or the desktop shortcut.
pause
