@echo off
setlocal EnableDelayedExpansion

:: ── Require admin ─────────────────────────────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

title Face Recognition System
color 0A
cd /d "%~dp0"

:: ── Check venv ────────────────────────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo.
    echo  ERROR: Virtual environment not found.
    echo  Please run SETUP.BAT first, then try again.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Face Recognition System
echo ============================================================
echo   URL  : http://localhost:5001
echo   Stop : Press Ctrl+C in this window
echo ============================================================
echo.

:: ── Open browser after 4 s ───────────────────────────────────────────────────
start "" powershell -WindowStyle Hidden -Command "Start-Sleep 4; Start-Process 'http://localhost:5001'"

:: ── Start server ─────────────────────────────────────────────────────────────
call venv\Scripts\activate.bat
python start.py

echo.
echo  Server stopped.
pause
