@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo [ERROR] Python virtual environment .venv not found.
    exit /b 1
)

.venv\Scripts\python -m pip install --upgrade pyinstaller
if errorlevel 1 exit /b 1

.venv\Scripts\python -m PyInstaller --noconfirm --clean LensBridgeAI.spec
if errorlevel 1 exit /b 1

echo.
echo Build completed: dist\LensBridgeAI.exe
endlocal
