@echo off
setlocal EnableExtensions
title IMDS v2.0 - Daily / Weekly Update

REM ============================================================
REM IMDS v2.0 launcher
REM Save this file in the project root: D:\IMDS_v2.0\Run_IMDS.bat
REM Double-click this BAT file whenever you want to run an update.
REM ============================================================

cd /d "%~dp0"
if errorlevel 1 (
    echo [ERROR] Could not open the IMDS project folder.
    pause
    exit /b 1
)

set "PROJECT_DIR=%~dp0"
set "VENV_PY=%PROJECT_DIR%.venv\Scripts\python.exe"
set "LOG_DIR=%PROJECT_DIR%logs"
set "LOG_FILE=%LOG_DIR%\imds_run_%DATE:~-4%%DATE:~4,2%%DATE:~7,2%.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo.
echo ============================================================
echo                 IMDS v2.0 UPDATE
echo ============================================================
echo Project: %PROJECT_DIR%
echo Log:     %LOG_FILE%
echo.

REM Find Python launcher
where py >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python launcher 'py' was not found.
    echo Install Python from https://www.python.org/downloads/
    echo During installation, enable the Python Launcher option.
    pause
    exit /b 1
)

REM Create virtual environment on first run
if not exist "%VENV_PY%" (
    echo [SETUP] Creating Python virtual environment...
    py -m venv "%PROJECT_DIR%.venv"
    if errorlevel 1 (
        echo [ERROR] Could not create virtual environment.
        pause
        exit /b 1
    )
)

REM Install/update required packages
if not exist "%PROJECT_DIR%requirements.txt" (
    echo [ERROR] requirements.txt was not found in the project root.
    echo Make sure this BAT file is inside D:\IMDS_v2.0.
    pause
    exit /b 1
)

echo [SETUP] Checking Python dependencies...
"%VENV_PY%" -m pip install --disable-pip-version-check -r "%PROJECT_DIR%requirements.txt"
if errorlevel 1 (
    echo [ERROR] Dependency installation failed. Check your internet connection and requirements.txt.
    pause
    exit /b 1
)

REM Check the main automation entry point
if not exist "%PROJECT_DIR%IMDS_auto_update.py" (
    echo [ERROR] IMDS_auto_update.py was not found.
    echo The project scaffold may not yet contain the completed automation script.
    echo No stock data was updated.
    pause
    exit /b 1
)

echo.
echo [RUN] Starting IMDS update...
echo [RUN] Started at %DATE% %TIME%
echo.

"%VENV_PY%" "%PROJECT_DIR%IMDS_auto_update.py" >> "%LOG_FILE%" 2>&1
set "RUN_RESULT=%ERRORLEVEL%"

echo.
if "%RUN_RESULT%"=="0" (
    echo [SUCCESS] IMDS update completed.
) else (
    echo [ERROR] IMDS update failed with exit code %RUN_RESULT%.
)
echo Finished at %DATE% %TIME%
echo Full output: "%LOG_FILE%"
echo.

pause
exit /b %RUN_RESULT%
