@echo off
setlocal EnableDelayedExpansion

title=TechBot A1 - Windows Installer (Fully Automated)
echo              ████████╗███████╗ ██████╗██╗  ██╗██████╗  ██████╗ ████████╗     █████╗  ██╗
echo              ╚══██╔══╝██╔════╝██╔════╝██║  ██║██╔══██╗██╔═══██╗╚══██╔══╝    ██╔══██╗███║
echo                 ██║   █████╗  ██║     ███████║██████╔╝██║   ██║   ██║       ███████║╚██║
echo                 ██║   ██╔══╝  ██║     ██╔══██║██╔══██╗██║   ██║   ██║       ██╔══██║ ██║
echo                 ██║   ███████╗╚██████╗██║  ██║██████╔╝╚██████╔╝   ██║       ██║  ██║ ██║
echo                 ╚═╝   ╚══════╝ ╚═════╝╚═╝  ╚═╝╚═════╝  ╚═════╝    ╚═╝       ╚═╝  ╚═╝ ╚═╝
echo        
echo                   ╔═════════════════════════════════════════════════════════════════╗
echo                   ║   PEN-TESTING AUTOMATED AI  //   Created by: EfaTheOne  v1.0.0  ║
echo                   ╚═════════════════════════════════════════════════════════════════╝
echo
echo                                            Automated Setup
echo
echo This script will check for Python, install it if missing,
echo install all required libraries, and start the app.
echo.
set "PYTHON_URL=https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe"
set "PYTHON_INSTALLER=%TEMP%\install_python.exe"

:: 1. Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] Python is not installed.
    echo [*] Downloading Python 3.11.8... This may take a moment.
    powershell -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'"
    
    echo [*] Installing Python silently... Please wait.
    %PYTHON_INSTALLER% /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1
    
    :: Refresh Environment variables for Python in the current session
    call "%TEMP%\refresh_env.cmd" 2>nul || echo.
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"
    
    python --version >nul 2>&1
    if !ERRORLEVEL! NEQ 0 (
        echo [X] Python installation failed. Please install Python manually from python.org and ensure "Add to PATH" is checked.
        pause
        exit /b 1
    )
    echo [+] Python installed successfully.
) else (
    echo [+] Python is already installed! Proceeding...
)

:: 2. Verify Project Files
echo.
echo [*] Checking project files...
if exist "techbot_gui.py" (
    echo [+] Running from project folder: %CD%
) else (
    echo [X] ERROR: Could not find techbot_gui.py.
    echo Please make sure you extract the entire downloaded ZIP file first,
    echo and run this script from inside the extracted folder.
    pause
    exit /b 1
)

:: 3. Setup Python Requirements
echo.
echo [*] Checking and installing required Python libraries...

python -m pip install --upgrade pip >nul 2>&1

if exist "requirements.txt" (
    echo [+] 'requirements.txt' found. Installing dependencies...
    pip install -r requirements.txt
) else (
    echo [!] 'requirements.txt' not found, attempting to install known major components...
    pip install customtkinter scapy pillow pynput pywifi
)

echo.
echo =========================================================
echo [+] INSTALLATION COMPLETE!
echo =========================================================
echo [*] Starting TechBot A1...
echo.

if exist "run_techbot.bat" (
    call run_techbot.bat
) else (
    python techbot_gui.py
)

pause
