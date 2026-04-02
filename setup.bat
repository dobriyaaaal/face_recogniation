@echo off
setlocal EnableDelayedExpansion

:: ── Require admin ─────────────────────────────────────────────────────────────
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs -Wait"
    exit /b
)

title Face Recognition System - Setup
color 0A
cd /d "%~dp0"

echo.
echo ============================================================
echo   Face Recognition System - First-Time Setup
echo ============================================================
echo.

:: ════════════════════════════════════════════════════════════════
:: STEP 1 — Find or install Python 3.11
:: ════════════════════════════════════════════════════════════════
echo [1/5] Checking for Python...
set "PYTHON_EXE="

:: Search known install locations in order of preference
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%PROGRAMFILES%\Python311\python.exe"
    "%PROGRAMFILES%\Python312\python.exe"
    "%PROGRAMFILES%\Python310\python.exe"
    "C:\Python311\python.exe"
    "C:\Python312\python.exe"
    "C:\Python310\python.exe"
) do (
    if exist %%P (
        set "PYTHON_EXE=%%~P"
        goto :python_found
    )
)

:: Try python / python3 from PATH
for %%C in (python python3) do (
    where %%C >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=%%C"
        goto :python_found
    )
)

:: ── Python not found: download & install Python 3.11.9 ─────────────────────
echo    Python not found. Downloading Python 3.11.9...
set "INSTALLER=%TEMP%\python-3.11.9-amd64.exe"
powershell -NoProfile -Command ^
    "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%INSTALLER%' -UseBasicParsing"

if not exist "%INSTALLER%" (
    echo.
    echo  ERROR: Could not download Python installer.
    echo  Please install Python 3.11 manually from https://www.python.org/downloads/
    echo  Make sure to tick "Add python.exe to PATH" during install, then re-run this script.
    echo.
    pause
    exit /b 1
)

echo    Installing Python 3.11.9 (this takes about 1 minute)...
"%INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 ^
    Include_tcltk=0 Include_test=0 ^
    TargetDir="%PROGRAMFILES%\Python311"
del "%INSTALLER%" >nul 2>&1

:: Explicitly add to PATH for this session
set "PATH=%PROGRAMFILES%\Python311;%PROGRAMFILES%\Python311\Scripts;%PATH%"

if exist "%PROGRAMFILES%\Python311\python.exe" (
    set "PYTHON_EXE=%PROGRAMFILES%\Python311\python.exe"
    goto :python_found
)

echo  ERROR: Python installation failed. Please install Python 3.11 manually.
pause
exit /b 1

:python_found
echo    Found: %PYTHON_EXE%
echo.

:: ════════════════════════════════════════════════════════════════
:: STEP 2 — Upgrade pip
:: ════════════════════════════════════════════════════════════════
echo [2/5] Upgrading pip...
:: Use python -m pip (not bare pip) — handles paths with spaces correctly
"%PYTHON_EXE%" -m pip install --upgrade pip --quiet --no-warn-script-location 2>nul
echo    pip OK
echo.

:: ════════════════════════════════════════════════════════════════
:: STEP 3 — Create virtual environment (skip if already exists)
:: ════════════════════════════════════════════════════════════════
echo [3/5] Setting up virtual environment...
if exist "venv\Scripts\activate.bat" (
    echo    Already exists, skipping.
) else (
    "%PYTHON_EXE%" -m venv venv
    if !errorlevel! neq 0 (
        echo  ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo    Created.
)
echo.

:: ════════════════════════════════════════════════════════════════
:: STEP 4 — Install Python packages
:: ════════════════════════════════════════════════════════════════
echo [4/5] Installing Python packages (may take 5-15 minutes)...
echo    (insightface AI models + OpenCV + FastAPI + FAISS)
echo.

call venv\Scripts\activate.bat
:: Use python -m pip throughout — avoids "path with spaces" errors on all pip calls
python -m pip install --upgrade pip --quiet --no-warn-script-location 2>nul

:: ── Step A: try onnxruntime-gpu FIRST so insightface sees it and doesn't ────
:: ── pull in the CPU-only onnxruntime as a dependency ─────────────────────────
echo    Pre-installing onnxruntime (GPU preferred)...
python -m pip install onnxruntime-gpu==1.15.1 --quiet --no-warn-script-location 2>nul
if !errorlevel! equ 0 (
    echo    onnxruntime-gpu 1.15.1 ready
    set "ORT_GPU=1"
) else (
    echo    onnxruntime-gpu not available on this platform, using CPU build...
    python -m pip install onnxruntime==1.15.1 --quiet --no-warn-script-location
    set "ORT_GPU=0"
)

:: ── Step B: install everything else ─────────────────────────────────────────
python -m pip install fastapi==0.111.0 "uvicorn[standard]==0.30.1" python-socketio==5.11.3 python-multipart==0.0.9 ^
    opencv-python==4.8.1.78 "numpy>=1.24.3,<2.0.0" insightface==0.7.3 pillow==10.0.0 ^
    faiss-cpu==1.8.0 pytz==2023.3 psutil onvif-zeep --no-warn-script-location

if !errorlevel! neq 0 (
    echo.
    echo  ERROR: Package installation failed.
    echo  Make sure you have an internet connection and try again.
    echo.
    pause
    exit /b 1
)

:: ── Step C: insightface sometimes re-pulls onnxruntime (CPU) as a dep ───────
:: ── Force-remove it and reinstall the GPU build if that's what we chose ──────
if "!ORT_GPU!"=="1" (
    echo    Ensuring onnxruntime-gpu is active (removing CPU build if present)...
    python -m pip uninstall onnxruntime -y --quiet 2>nul
    python -m pip install onnxruntime-gpu==1.15.1 --quiet --no-warn-script-location 2>nul
    echo    GPU build confirmed
)
echo.
echo    All packages installed.
echo.

:: ════════════════════════════════════════════════════════════════
:: STEP 5 — Pre-download AI models (~380 MB, one-time only)
:: ════════════════════════════════════════════════════════════════
echo [5/5] Downloading AI face recognition models...
echo    (antelopev2 — ArcFace R100, ~380 MB — this only happens once)
echo.

python -c "from insightface.app import FaceAnalysis; a=FaceAnalysis(name='antelopev2'); a.prepare(ctx_id=-1, det_size=(640,640)); print('   Models ready')"

if !errorlevel! neq 0 (
    echo.
    echo  WARNING: Model download failed. The system will try again on first launch.
    echo  Make sure you have ~400MB free and an internet connection when first running.
    echo.
)

:: ════════════════════════════════════════════════════════════════
:: Create required data directories
:: ════════════════════════════════════════════════════════════════
if not exist "webapp\people"     mkdir "webapp\people"
if not exist "webapp\embeddings" mkdir "webapp\embeddings"
if not exist "webapp\gallery"    mkdir "webapp\gallery"

:: ════════════════════════════════════════════════════════════════
:: CUDA CHECK — detect NVIDIA GPU and whether CUDA is installed
:: ════════════════════════════════════════════════════════════════
set "HAS_NVIDIA=0"
set "HAS_CUDA=0"
set "CUDA_VER="

:: Check for any NVIDIA GPU via nvidia-smi
nvidia-smi >nul 2>&1
if !errorlevel! equ 0 (
    set "HAS_NVIDIA=1"
    :: Extract CUDA version from nvidia-smi output
    for /f "tokens=*" %%L in ('nvidia-smi ^| findstr /i "CUDA Version"') do (
        set "CUDA_LINE=%%L"
    )
)

:: Check if CUDA toolkit is installed (nvcc = the compiler)
nvcc --version >nul 2>&1
if !errorlevel! equ 0 (
    set "HAS_CUDA=1"
    for /f "tokens=5 delims= " %%V in ('nvcc --version ^| findstr /i "release"') do (
        set "CUDA_VER=%%V"
    )
)

echo.
echo ============================================================
echo   GPU / CUDA Status
echo ============================================================

if "!HAS_NVIDIA!"=="0" (
    echo.
    echo   No NVIDIA GPU detected.
    echo   The system will run on CPU — performance is reduced but fully functional.
    echo.
    echo   If you DO have an NVIDIA GPU and this is wrong:
    echo     - Update your NVIDIA drivers from:
    echo       https://www.nvidia.com/Download/index.aspx
    echo     - Then re-run SETUP.BAT
    echo.
) else (
    echo.
    echo   NVIDIA GPU detected.  !CUDA_LINE!
    echo.
    if "!HAS_CUDA!"=="1" (
        echo   CUDA Toolkit is installed  ^(nvcc version: !CUDA_VER!^)
        echo   GPU acceleration is ACTIVE. Detection will be fast.
        echo.
    ) else (
        echo   *** CUDA Toolkit is NOT installed ***
        echo   Your GPU ^(RTX 3050 / NVIDIA^) is present but CUDA is missing.
        echo   Without CUDA the system falls back to CPU — much slower.
        echo.
        echo   ── HOW TO ENABLE GPU ACCELERATION ──────────────────────────
        echo.
        echo   STEP 1 — Install CUDA Toolkit 11.8  ^(required by this app^)
        echo     Download: https://developer.nvidia.com/cuda-11-8-0-download-archive
        echo     Choose:   Windows ^> x86_64 ^> 11 ^> exe ^(local^)
        echo     Install with default settings.
        echo.
        echo   STEP 2 — Install cuDNN 8.x for CUDA 11.8  ^(speeds up AI models^)
        echo     Download: https://developer.nvidia.com/rdp/cudnn-archive
        echo     ^(free NVIDIA account required^)
        echo     Get:  cuDNN v8.9.x for CUDA 11.x  ^> Local Installer for Windows
        echo     After unzipping, copy the 3 folders into:
        echo       C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8\
        echo         bin\      ^<-- copy cudnn*.dll here
        echo         include\  ^<-- copy cudnn*.h here
        echo         lib\x64\  ^<-- copy cudnn*.lib here
        echo.
        echo   STEP 3 — Update NVIDIA GPU drivers  ^(if not done recently^)
        echo     Download: https://www.nvidia.com/Download/index.aspx
        echo     Select your GPU model and install.
        echo.
        echo   STEP 4 — Re-run this SETUP.BAT after the above installs.
        echo     onnxruntime-gpu is already installed in the venv.
        echo     It will auto-detect CUDA on next run — no changes to app needed.
        echo.
        echo   ── QUICK LINKS ─────────────────────────────────────────────
        echo     CUDA 11.8:  https://developer.nvidia.com/cuda-11-8-0-download-archive
        echo     cuDNN:      https://developer.nvidia.com/rdp/cudnn-archive
        echo     Drivers:    https://www.nvidia.com/Download/index.aspx
        echo     Guide:      https://docs.nvidia.com/cuda/cuda-installation-guide-microsoft-windows/
        echo   ────────────────────────────────────────────────────────────
        echo.
        echo   NOTE: The app works RIGHT NOW on CPU. Install CUDA only if you
        echo         want faster real-time detection on multiple cameras.
        echo.
        :: Open the CUDA download page automatically in the browser
        echo   Opening CUDA 11.8 download page in your browser...
        start "" "https://developer.nvidia.com/cuda-11-8-0-download-archive"
        echo.
    )
)

echo ============================================================
echo   Setup Complete!
echo.
echo   Double-click START.BAT to launch the application.
echo   The browser will open automatically at http://localhost:5001
echo ============================================================
echo.
pause
