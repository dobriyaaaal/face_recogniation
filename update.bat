@echo off
setlocal EnableDelayedExpansion

:: ════════════════════════════════════════════════════════════════
::  SET THIS — your public GitHub repo URL
:: ════════════════════════════════════════════════════════════════
set "REPO_URL=https://github.com/dobriyaaaal/face_recogniation.git"

:: ── Require admin ────────────────────────────────────────────────────────────
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
        "!GIT_INSTALLER!" /VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS
        del "!GIT_INSTALLER!" >nul 2>&1
        set "PATH=%PROGRAMFILES%\Git\cmd;%PATH%"
        echo   Git installed.
    ) else (
        echo.
        echo   ERROR: Could not download Git.
        echo   Please install manually: https://git-scm.com/download/win
        start "" "https://git-scm.com/download/win"
        pause
        exit /b 1
    )
) else (
    echo   Git found.
)
echo.

:: ════════════════════════════════════════════════════════════════
:: Pull latest code (or clone if first time)
:: ════════════════════════════════════════════════════════════════
echo [2/3] Pulling latest code from GitHub...

if exist ".git" (
    git pull
) else (
    :: Not a git repo yet — this must be the unzipped version
    :: Clone fresh next to this folder, then move files over
    set "CLONE_DIR=%TEMP%\face_rec_update_clone"
    if exist "!CLONE_DIR!" rmdir /s /q "!CLONE_DIR!"
    git clone "%REPO_URL%" "!CLONE_DIR!"
    if !errorlevel! neq 0 (
        echo.
        echo   ERROR: Could not clone from GitHub. Check your internet connection.
        pause
        exit /b 1
    )
    robocopy "!CLONE_DIR!" "%~dp0" /E /XD venv .git ^
        /XD "webapp\people" "webapp\embeddings" "webapp\gallery" ^
        /XF "*.db" /NFL /NDL /NJH /NJS >nul
    robocopy "!CLONE_DIR!\.git" "%~dp0\.git" /E /NFL /NDL /NJH /NJS >nul
    rmdir /s /q "!CLONE_DIR!" >nul 2>&1
    echo   Repository initialized.
)

if !errorlevel! neq 0 (
    echo.
    echo   ERROR: git pull failed. Check your internet connection.
    pause
    exit /b 1
)
echo   Code updated.
echo.

:: ════════════════════════════════════════════════════════════════
:: Update Python packages
:: ════════════════════════════════════════════════════════════════
echo [3/3] Checking Python packages...

if not exist "venv\Scripts\activate.bat" (
    echo   Virtual environment not found. Running full setup...
    call setup.bat
    exit /b
)

call venv\Scripts\activate.bat
python -m pip install -r requirements.txt --quiet --no-warn-script-location 2>nul
echo   Packages up to date.
echo.

echo ============================================================
echo   Update complete!
echo.
echo   Double-click START.BAT to launch the application.
echo ============================================================
echo.
pause
::
::  Google Drive:
::    1. Upload the zip → right-click → Share → "Anyone with the link"
::    2. Copy the link  (looks like: https://drive.google.com/file/d/XXXX/view)
::    3. Paste it below — this script converts it to a direct download automatically
::
::  OneDrive:
::    1. Upload the zip → Share → "Anyone with the link" → Copy
::    2. Paste it below as-is
:: ════════════════════════════════════════════════════════════════
set "SHARE_URL=PASTE_YOUR_LINK_HERE"

:: ── Require admin ────────────────────────────────────────────────────────────
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
:: Sanity check — make sure the URL has been set
:: ════════════════════════════════════════════════════════════════
if "!SHARE_URL!"=="PASTE_YOUR_LINK_HERE" (
    echo   ERROR: No update URL configured.
    echo   Open update.bat in Notepad and paste your Google Drive or
    echo   OneDrive share link into the SHARE_URL variable at the top.
    echo.
    pause
    exit /b 1
)

:: ════════════════════════════════════════════════════════════════
:: Convert Google Drive share link → direct download URL
:: ════════════════════════════════════════════════════════════════
set "DOWNLOAD_URL=!SHARE_URL!"

echo !SHARE_URL! | findstr /i "drive.google.com/file/d/" >nul
if !errorlevel! equ 0 (
    :: Extract the file ID between /d/ and the next /
    for /f "tokens=6 delims=/" %%I in ("!SHARE_URL!") do set "GDRIVE_ID=%%I"
    :: Strip any query string from the ID
    for /f "tokens=1 delims=?" %%I in ("!GDRIVE_ID!") do set "GDRIVE_ID=%%I"
    set "DOWNLOAD_URL=https://drive.google.com/uc?export=download&confirm=t&id=!GDRIVE_ID!"
    echo   Google Drive link detected. File ID: !GDRIVE_ID!
)

echo !SHARE_URL! | findstr /i "1drv.ms\|onedrive.live.com\|sharepoint.com" >nul
if !errorlevel! equ 0 (
    :: OneDrive: replace the last part to force direct download
    set "DOWNLOAD_URL=!SHARE_URL!"
    echo !SHARE_URL! | findstr /i "download=1" >nul
    if !errorlevel! neq 0 (
        set "DOWNLOAD_URL=!SHARE_URL!&download=1"
    )
    echo   OneDrive link detected.
)

:: ════════════════════════════════════════════════════════════════
:: Step 1 — Download the update zip
:: ════════════════════════════════════════════════════════════════
echo.
echo [1/3] Downloading update...
set "ZIP_TEMP=%TEMP%\face_rec_update.zip"

powershell -NoProfile -Command ^
    "try { Invoke-WebRequest -Uri '!DOWNLOAD_URL!' -OutFile '!ZIP_TEMP!' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"

if !errorlevel! neq 0 (
    echo.
    echo   ERROR: Download failed.
    echo   - Check your internet connection
    echo   - Make sure the share link is set to 'Anyone with the link can view'
    echo   - Try opening this URL in your browser to test it:
    echo     !DOWNLOAD_URL!
    echo.
    pause
    exit /b 1
)

if not exist "!ZIP_TEMP!" (
    echo   ERROR: Downloaded file not found. The link may have expired.
    pause
    exit /b 1
)

echo   Download complete.
echo.

:: ════════════════════════════════════════════════════════════════
:: Step 2 — Extract (preserve user data: venv, people, embeddings, gallery)
:: ════════════════════════════════════════════════════════════════
echo [2/3] Applying update...

:: Extract to a temp staging folder
set "STAGE_DIR=%TEMP%\face_rec_stage"
if exist "!STAGE_DIR!" rmdir /s /q "!STAGE_DIR!"

powershell -NoProfile -Command ^
    "Expand-Archive -Path '!ZIP_TEMP!' -DestinationPath '!STAGE_DIR!' -Force"

if !errorlevel! neq 0 (
    echo   ERROR: Failed to extract the update zip.
    del "!ZIP_TEMP!" >nul 2>&1
    pause
    exit /b 1
)

:: Find the root folder inside the zip (handles any folder name)
set "STAGE_ROOT="
for /d %%D in ("!STAGE_DIR!\*") do (
    if not defined STAGE_ROOT set "STAGE_ROOT=%%D"
)

if not defined STAGE_ROOT (
    echo   ERROR: Could not find content inside the zip.
    pause
    exit /b 1
)

:: Copy new code files — explicitly skip user data folders
robocopy "!STAGE_ROOT!" "%~dp0" /E /XD venv .git ^
    /XD "webapp\people" "webapp\embeddings" "webapp\gallery" ^
    /XF "*.db" /NFL /NDL /NJH /NJS >nul

:: Cleanup temp files
rmdir /s /q "!STAGE_DIR!" >nul 2>&1
del "!ZIP_TEMP!" >nul 2>&1

echo   Files updated.
echo.

:: ════════════════════════════════════════════════════════════════
:: Step 3 — Update Python packages (catches any new dependencies)
:: ════════════════════════════════════════════════════════════════
echo [3/3] Checking Python packages...

if not exist "venv\Scripts\activate.bat" (
    echo   Virtual environment not found. Running full setup first...
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
echo ============================================================
echo   Update complete!
echo.
echo   Double-click START.BAT to launch the application.
echo ============================================================
echo.
pause
