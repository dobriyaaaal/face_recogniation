@echo off
echo Setting up Face Recognition System...
echo.

echo Installing Python requirements...
pip install -r requirements.txt

echo.
echo Creating directories...
if not exist "people" mkdir people
if not exist "embeddings" mkdir embeddings
if not exist "gallery" mkdir gallery

echo.
echo Setup complete! 
echo.
echo To start the system:
echo   cd webapp
echo   python start.py
echo.
pause
