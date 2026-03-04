@echo off
:: TechBot Applications Master Launcher
title TechBot Applications - Master Launcher
color 0A

:menu
cls
echo.
echo  =======================================================
echo  =                                                     =
echo  =          TECHBOT APPLICATIONS LAUNCHER              =
echo  =              Optimized Edition v2.0                 =
echo  =                                                     =
echo  =======================================================
echo.
echo  Select an application to launch:
echo.
echo  [1] TechBot Code Editor (VS Code-like)
echo      - Professional code editor
echo      - Syntax highlighting
echo      - Multi-file support
echo      - Memory optimized
echo.
echo  [2] TechBot Games Arcade
echo      - 6 fun games included
echo      - Snake, Pong, Tic Tac Toe
echo      - Memory Match, Reaction Time, Number Guesser
echo.
echo  [3] TechBot AI Assistant (Original)
echo      - Full pentesting suite
echo      - AI-powered assistance
echo      - Network tools
echo.
echo  [4] View README (New Apps Info)
echo.
echo  [5] TechBot Autonomous Agent (AI)
echo      - Full AI desktop agent
echo      - Vision-based screen control
echo      - Task planning and execution
echo.
echo  [0] Exit
echo.
echo  -------------------------------------------------------
set /p choice="  Enter your choice (0-5): "

if "%choice%"=="1" goto code_editor
if "%choice%"=="2" goto games
if "%choice%"=="3" goto techbot
if "%choice%"=="4" goto readme
if "%choice%"=="5" goto agent
if "%choice%"=="0" goto exit
goto menu

:code_editor
cls
echo.
echo  Launching TechBot Code Editor...
echo.
python techbot_code_editor.py
goto menu

:games
cls
echo.
echo  Launching TechBot Games Arcade...
echo.
python techbot_games.py
goto menu

:techbot
cls
echo.
echo  Launching TechBot AI Assistant...
echo.
python techbot_gui.py
goto menu

:readme
cls
type NEW_APPS_README.md
echo.
pause
goto menu

:agent
cls
echo.
echo  Launching TechBot Autonomous Agent...
echo.
python techbot_agent.py
goto menu

:exit
cls
echo.
echo  Thank you for using TechBot Applications!
echo  Goodbye!
echo.
timeout /t 2 >nul
exit
