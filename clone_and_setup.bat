@echo off
setlocal EnableDelayedExpansion

:: ── Require admin ─────────────────────────────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs -Wait"
    exit /b
)

title Face Recognition System - First Install
color 0A

echo.
echo ============================================================
echo   Face Recognition System - First-Time Install
echo ============================================================
echo.

:: ════════════════════════════════════════════════════════════════
:: SET THIS: your GitHub repo URL (update before sharing this file)
:: ════════════════════════════════════════════════════════════════
set "REPO_URL=https://github.com/YOUR_USERNAME/face_recogniation.git"
set "INSTALL_DIR=%USERPROFILE%\FaceRecognitionSystem"

:: ════════════════════════════════════════════════════════════════
:: Check / install Git
:: ════════════════════════════════════════════════════════════════
echo [1/3] Checking for Git...
where git >nul 2>&1
if !errorlevel! neq 0 (
    echo   Git not found. Downloading Git for Windows...
    set "GIT_INSTALLER=%TEMP%\git-installer.exe"
    powershell -NoProfile -Command ^
        "Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/v2.44.0.windows.1/Git-2.44.0-64-bit.exe' -OutFile '!GIT_INSTALLER!' -UseBasicParsing"
    if exist "!GIT_INSTALLER!" (
        echo   Installing Git silently...
        "!GIT_INSTALLER!" /VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /COMPONENTS="icons,ext\reg\shellhere,assoc,assoc_sh"
        del "!GIT_INSTALLER!" >nul 2>&1
        :: Reload PATH
        set "PATH=%PROGRAMFILES%\Git\cmd;%PATH%"
        echo   Git installed.
    ) else (
        echo.
        echo   ERROR: Could not download Git.
        echo   Please install manually: https://git-scm.com/download/win
        echo   Then re-run this script.
        start "" "https://git-scm.com/download/win"
        pause
        exit /b 1
    )
) else (
    echo   Git found.
)
echo.

:: ════════════════════════════════════════════════════════════════
:: Clone the repo
:: ════════════════════════════════════════════════════════════════
echo [2/3] Downloading Face Recognition System...

if exist "%INSTALL_DIR%\.git" (
    echo   Already installed at %INSTALL_DIR%, updating instead...
    cd /d "%INSTALL_DIR%"
    git pull
) else (
    git clone "%REPO_URL%" "%INSTALL_DIR%"
    if !errorlevel! neq 0 (
        echo.
        echo   ERROR: Could not clone the repository.
        echo   Make sure:
        echo     - You have internet access
        echo     - You have been added as a collaborator on GitHub
        echo     - You enter your GitHub username and Personal Access Token when prompted
        echo.
        echo   How to create a Personal Access Token:
        echo     https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
        echo.
        pause
        exit /b 1
    )
)
echo   Download complete.
echo.

:: ════════════════════════════════════════════════════════════════
:: Run setup
:: ════════════════════════════════════════════════════════════════
echo [3/3] Running setup...
cd /d "%INSTALL_DIR%"
call setup.bat
