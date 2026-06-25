@echo off
echo =============================================================
echo          LensBridge AI Launcher
echo =============================================================
echo.

if not exist .venv\Scripts\python.exe (
    echo [ERROR] Python virtual environment .venv not found!
    echo Please set up the environment and install dependencies first.
    echo.
    pause
    exit /b
)

echo [1/2] Starting Backend Server in a new window...
start "LensBridge AI Backend Server" cmd /k ".venv\Scripts\python server\app.py"

ping -n 3 127.0.0.1 > nul

echo [2/2] Starting Client Mouse Listener...
echo.
echo =============================================================
echo Client is ready! Listening for mouse holds...
echo =============================================================
echo.

.venv\Scripts\python client\client.py

pause
