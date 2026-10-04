@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   IngeTrazo MultiView Extension Installer
echo ===================================================
echo.

set "TARGET_DIR=%APPDATA%\ingetrazo\plugins"

if not exist "%TARGET_DIR%" (
    echo Creating plugins directory: "%TARGET_DIR%"
    mkdir "%TARGET_DIR%"
)

echo Installing ingetrazo_multiview.py to "%TARGET_DIR%"...
copy /Y "%~dp0ingetrazo_multiview.py" "%TARGET_DIR%\" >nul

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] IngeTrazo MultiView installed successfully!
    echo Start or restart IngeTrazo to use the new MultiView extension.
    echo.
) else (
    echo.
    echo [ERROR] Installation failed.
    echo Please manually copy ingetrazo_multiview.py to:
    echo %TARGET_DIR%
    echo.
)

pause
