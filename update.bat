@echo off
setlocal EnableDelayedExpansion

:: ── Require admin ─────────────────────────────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs -Wait"
    exit /b
)

title Face Recognition System - Update
color 0A
cd /d "%~dp0"

echo.
echo ============================================================
echo   Face Recognition System - Updater
echo ============================================================
echo.

:: ════════════════════════════════════════════════════════════════
:: Check git is available
:: ════════════════════════════════════════════════════════════════
where git >nul 2>&1
if !errorlevel! neq 0 (
    echo   Git is not installed.
    echo.
    echo   Please install Git for Windows, then re-run this script:
    echo     https://git-scm.com/download/win
    echo.
    echo   Opening download page...
    start "" "https://git-scm.com/download/win"
    pause
    exit /b 1
)

:: ════════════════════════════════════════════════════════════════
:: Pull latest code
:: ════════════════════════════════════════════════════════════════
echo [1/3] Pulling latest code from GitHub...
git pull
if !errorlevel! neq 0 (
    echo.
    echo   ERROR: git pull failed.
    echo   Make sure you have internet access and your GitHub credentials are set up.
    echo   If prompted for a password, use a Personal Access Token, not your GitHub password.
    echo     How to create one: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
    echo.
    pause
    exit /b 1
)
echo   Code updated.
echo.

:: ════════════════════════════════════════════════════════════════
:: Update Python packages (in case requirements changed)
:: ════════════════════════════════════════════════════════════════
echo [2/3] Checking Python packages...

if not exist "venv\Scripts\activate.bat" (
    echo   Virtual environment not found. Running full setup...
    call setup.bat
    exit /b
)

call venv\Scripts\activate.bat
python -m pip install -r requirements.txt --quiet --no-warn-script-location 2>nul
echo   Packages up to date.
echo.

:: ════════════════════════════════════════════════════════════════
:: Done
:: ════════════════════════════════════════════════════════════════
echo [3/3] Done.
echo.
echo ============================================================
echo   Update complete!
echo.
echo   Run START.BAT to launch the application.
echo ============================================================
echo.
pause
