@echo off
echo ========================================
echo    Invoice Generator - Startup Script
echo ========================================
echo.

:: Check if venv exists, create if not
if not exist "venv" (
    echo [*] Virtual environment not found. Creating...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
    echo [+] Virtual environment created successfully!
) else (
    echo [+] Virtual environment found.
)

echo.
echo [*] Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo [*] Installing/Updating requirements...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install requirements!
    pause
    exit /b 1
)

echo.
echo ========================================
echo [*] Starting the application...
echo ========================================
echo.
python app.py

pause
