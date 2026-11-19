@echo off
setlocal
cd /d "%~dp0"
echo ======================================================
echo AGENTOPIA - Local Development Server
 echo Do not paste real private keys into the app or share them.
echo ======================================================
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PYTHON=py -3"
) else (
    set "PYTHON=python"
)
if not exist ".venv\Scripts\python.exe" (
    %PYTHON% -m venv .venv
    if errorlevel 1 goto failed
)
call .venv\Scripts\activate.bat
python -m pip install -r requirements-dev.txt
if errorlevel 1 goto failed
echo.
echo Open http://127.0.0.1:8000 in your browser
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
exit /b 0
:failed
echo Setup failed. See README.md for installation requirements.
pause
exit /b 1
