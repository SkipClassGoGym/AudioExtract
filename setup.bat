@echo off
setlocal
cd /d "%~dp0"
echo Setting up AudioExtract...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements-gpu.txt
if errorlevel 1 goto failed
echo.
echo Ready. Open Start AudioExtract.vbs to launch.
pause
exit /b 0
:failed
echo.
echo Setup failed. Install Python 3.10 or later (64-bit) and check your Internet connection.
pause
exit /b 1
